"""Transformation Jobs REST API router with SSE streaming and resource authorization."""

import json
import logging
import re
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ...auth.config import auth_config
from ...auth.dependencies import authorize_resource, get_current_user
from ...config import settings
from ...db.connection import get_connection
from ...db.repositories.artifact_repo import ArtifactRepository
from ...db.repositories.job_repo import JobRepository
from ...exceptions import BadRequestError, EntityNotFoundError, InvalidStateError, StorageError
from ...models.artifact import Artifact
from ...models.content import CanonicalContent
from ...models.enums import ArtifactType, JobState, OutputFormat, ValidationStatus
from ...models.job import TransformationJob
from ...models.transformation_events import TransformationEventType
from ...models.user import User
from ...services.artifact_service import artifact_service
from ...services.job_service import job_service
from ...services.source_service import source_service
from ...services.transformation.event_broker import event_broker
from ...storage.service import storage_service

logger = logging.getLogger("limo.api.jobs")

router = APIRouter(prefix="/jobs", tags=["Jobs"])


class JobCallbackPayload(BaseModel):
    """Payload sent by background worker (local turbo or GitHub Actions runner)."""
    job_id: str
    execution_id: str
    attempt: int = 1
    github_run_id: Optional[str] = None
    status: str = "completed"  # "running" | "completed" | "failed" | "cancelled"
    artifact_id: Optional[str] = None
    storage_ref: Optional[str] = None
    size_bytes: Optional[int] = 0
    sha256: Optional[str] = None
    content_hash: Optional[str] = None
    mime_type: Optional[str] = None
    filename: Optional[str] = None
    error_message: Optional[str] = None


def _verify_worker_access(worker_key: Optional[str]) -> bool:
    """Verify worker authentication token using constant-time comparison. Fail closed."""
    import hmac
    expected_token = (settings.resolved_worker_token or "").strip()
    if not expected_token:
        if settings.limo_surface.lower() == "web":
            logger.error("WORKER_AUTH_TOKEN is not configured on web surface - failing closed")
        return False
    if not worker_key or not worker_key.strip():
        return False
    return hmac.compare_digest(worker_key.strip(), expected_token)


@router.get("", response_model=List[TransformationJob])
async def list_jobs(
    project_id: Optional[str] = Query(None, description="Filter jobs by project"),
    session_id: Optional[str] = Query(None, description="Filter jobs by chat session"),
    state: Optional[JobState] = Query(None, description="Filter jobs by lifecycle state"),
    current_user: User = Depends(get_current_user),
) -> List[TransformationJob]:
    """List transformation jobs with optional filtering, scoped to user on web surface."""
    user_scope = current_user.id if auth_config.is_web_surface else None
    return job_service.list_jobs(
        project_id=project_id,
        session_id=session_id,
        state=state,
        user_id=user_scope,
    )


@router.get("/{job_id}", response_model=TransformationJob)
async def get_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> TransformationJob:
    """Retrieve job execution status, progress, stage, and deliverables."""
    job = job_service.get_job(job_id)
    authorize_resource(job.user_id, current_user)
    return job


@router.post("/{job_id}/cancel", response_model=TransformationJob)
async def cancel_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
) -> TransformationJob:
    """Cancel an active or queued transformation job with cooperative worker signaling."""
    job = job_service.get_job(job_id)
    authorize_resource(job.user_id, current_user)
    return job_service.cancel_job(job_id)


@router.get("/{job_id}/context")
async def get_job_context(
    job_id: str,
    x_limo_worker_key: Optional[str] = Header(None, alias="X-Limo-Worker-Key"),
    x_limo_execution_id: Optional[str] = Header(None, alias="X-Limo-Execution-ID"),
) -> Dict[str, Any]:
    """Retrieve lightweight generation context for cloud worker rendering."""
    # Worker authentication check
    if not _verify_worker_access(x_limo_worker_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing worker authentication key",
        )

    job = job_service.get_job(job_id)

    # Extract format and configuration details
    title = job.prompt or "Deliverable Render"
    user_directive = job.prompt or ""
    aspect_ratio = "3:4"
    if job.configuration:
        if job.configuration.infographic and job.configuration.infographic.aspect_ratio:
            aspect_ratio = job.configuration.infographic.aspect_ratio

    # Retrieve sources or facts if present
    sources_summary = []
    for src_id in job.source_ids:
        try:
            src = source_service.get_source(src_id)
            sources_summary.append({"id": src.id, "name": src.name, "mime_type": src.mime_type})
        except Exception:
            pass

    return {
        "job_id": job.id,
        "project_id": job.project_id,
        "title": title,
        "prompt": user_directive,
        "aspect_ratio": aspect_ratio,
        "requested_formats": [f.value for f in job.requested_formats],
        "sources": sources_summary,
        "execution_id": x_limo_execution_id or job.execution_id,
    }


@router.post("/{job_id}/upload")
async def upload_job_artifact(
    job_id: str,
    file: UploadFile = File(...),
    execution_id: Optional[str] = Form(None),
    artifact_id: Optional[str] = Form(None),
    sha256: Optional[str] = Form(None),
    content_hash: Optional[str] = Form(None),
    mime_type: Optional[str] = Form(None),
    x_limo_worker_key: Optional[str] = Header(None, alias="X-Limo-Worker-Key"),
) -> Dict[str, Any]:
    """Direct deliverable file upload endpoint for workers with cryptographic storage."""
    if not _verify_worker_access(x_limo_worker_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing worker authentication key",
        )

    # Ensure job exists
    job = job_service.get_job(job_id)

    art_id = artifact_id or f"art_gh_{uuid.uuid4().hex[:12]}"
    filename = file.filename or f"{art_id}.bin"

    try:
        storage_ref, size_bytes, computed_sha256 = await storage_service.save_artifact_stream(
            artifact_id=art_id,
            filename=filename,
            upload_file=file,
        )
    except Exception as exc:
        logger.error("Failed to stream upload for job %s: %s", job_id, exc)
        raise HTTPException(status_code=400, detail=f"File upload failed: {exc}")

    # Authoritative verification against worker-provided hash if supplied
    worker_hash = (content_hash or sha256 or "").strip().lower()
    if worker_hash:
        if worker_hash != computed_sha256:
            storage_service.delete_file(storage_ref)
            logger.warning(
                "Upload SHA-256 mismatch for job %s, artifact %s: worker reported '%s', backend computed '%s'",
                job_id,
                art_id,
                worker_hash,
                computed_sha256,
            )
            raise HTTPException(
                status_code=400,
                detail=f"Content hash verification failed: worker reported {worker_hash}, backend computed {computed_sha256}",
            )

    logger.info(
        "Received verified worker file upload for job %s: art_id=%s, size=%d bytes, ref=%s, sha256=%s",
        job_id,
        art_id,
        size_bytes,
        storage_ref,
        computed_sha256[:8],
    )

    return {
        "artifact_id": art_id,
        "storage_ref": storage_ref,
        "size_bytes": size_bytes,
        "sha256": computed_sha256,
        "content_hash": computed_sha256,
        "filename": filename,
    }


@router.post("/{job_id}/callback")
async def worker_job_callback(
    job_id: str,
    payload: JobCallbackPayload,
    x_limo_worker_key: Optional[str] = Header(None, alias="X-Limo-Worker-Key"),
) -> Dict[str, Any]:
    """Atomic, idempotent callback endpoint for background & cloud worker executions."""
    if not _verify_worker_access(x_limo_worker_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing worker authentication key",
        )

    job = job_service.get_job(job_id)
    cb_status = (payload.status or "completed").lower()

    logger.info(
        "Received worker callback for job %s: status=%s, exec_id=%s, run_id=%s, attempt=%s",
        job_id,
        cb_status,
        payload.execution_id,
        payload.github_run_id,
        payload.attempt,
    )

    # 1. Stale execution validation gate
    active_exec_id = getattr(job, "execution_id", None)
    if active_exec_id and payload.execution_id and payload.execution_id != active_exec_id:
        logger.warning(
            "Rejecting stale execution callback for job %s: active execution is '%s', received '%s'",
            job_id,
            active_exec_id,
            payload.execution_id,
        )
        return {
            "status": "ignored",
            "reason": "stale_execution_id",
            "active_execution_id": active_exec_id,
            "received_execution_id": payload.execution_id,
        }

    # 2. Outdated attempt validation gate
    current_attempt = 1
    if job.configuration and isinstance(job.configuration.format_overrides, dict):
        current_attempt = job.configuration.format_overrides.get("attempt", 1)
    if payload.attempt and payload.attempt < current_attempt:
        logger.warning(
            "Rejecting stale attempt callback for job %s: current attempt is %d, received %d",
            job_id,
            current_attempt,
            payload.attempt,
        )
        return {
            "status": "ignored",
            "reason": "stale_attempt",
            "current_attempt": current_attempt,
            "received_attempt": payload.attempt,
        }

    # 3. Terminal state protection: prevent resurrection of cancelled or failed jobs
    if job.state == JobState.CANCELLED:
        logger.info("Ignoring callback for already cancelled job %s", job_id)
        return {"status": "ignored", "reason": "job_already_cancelled", "job_id": job_id}

    if job.state == JobState.FAILED:
        logger.info("Ignoring callback for already failed job %s", job_id)
        return {"status": "ignored", "reason": "job_already_failed", "job_id": job_id}

    # 4. Strict idempotency check for already completed jobs
    if job.state == JobState.COMPLETED:
        existing_art_id = payload.artifact_id or (job.artifact_ids[0] if job.artifact_ids else None)
        logger.info("Duplicate completed callback ignored for job %s (strictly idempotent)", job_id)
        return {
            "status": "completed",
            "job_id": job_id,
            "artifact_id": existing_art_id,
            "duplicate": True,
        }

    if cb_status == "running":
        # Report start / update status with github_run_id
        if payload.github_run_id:
            with get_connection() as conn:
                JobRepository.update_job_progress(
                    conn=conn,
                    job_id=job_id,
                    state=JobState.PROCESSING,
                    progress=max(job.progress, 0.25),
                    current_stage=f"Cloud render executing (GitHub Run {payload.github_run_id})",
                )
        return {"status": "acknowledged", "job_id": job_id, "state": "processing"}

    elif cb_status == "completed":
        artifact_id = payload.artifact_id or f"art_gh_{payload.execution_id}"
        is_video = bool(payload.filename and payload.filename.endswith(".mp4")) or (
            payload.mime_type and "video" in payload.mime_type
        )
        art_type = ArtifactType.VIDEO if is_video else ArtifactType.INFOGRAPHIC
        file_ext = ".mp4" if is_video else ".png"

        # 1. Enforce 64-char lowercase hexadecimal content_hash requirement
        worker_hash = (payload.content_hash or payload.sha256 or "").strip().lower()
        if not worker_hash or len(worker_hash) != 64 or not re.match(r"^[0-9a-f]{64}$", worker_hash):
            raise HTTPException(
                status_code=400,
                detail="content_hash is required and must be a valid 64-character hexadecimal SHA-256 digest",
            )

        # 2. Resolve storage reference
        default_filename = payload.filename or (f"{artifact_id}.mp4" if is_video else f"{artifact_id}.png")
        storage_ref = payload.storage_ref or f"artifacts/{artifact_id}/{default_filename}"

        # 3. Storage resolution and hash verification
        actual_size = payload.size_bytes or 0

        if storage_service.file_exists(storage_ref):
            backend_hash, actual_size = storage_service.compute_file_sha256(storage_ref)
            if backend_hash != worker_hash:
                raise HTTPException(
                    status_code=400,
                    detail=f"Content hash mismatch: worker reported '{worker_hash}', storage contains '{backend_hash}'",
                )
        else:
            # Check alternative relative path under artifacts/
            alt_ref = f"artifacts/{artifact_id}/{default_filename}"
            if storage_service.file_exists(alt_ref):
                storage_ref = alt_ref
                backend_hash, actual_size = storage_service.compute_file_sha256(storage_ref)
                if backend_hash != worker_hash:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Content hash mismatch: worker reported '{worker_hash}', storage contains '{backend_hash}'",
                    )
            elif not storage_ref.startswith("worker://"):
                raise HTTPException(
                    status_code=400,
                    detail=f"Referenced deliverable file '{storage_ref}' does not exist in storage",
                )

        # 4. Authoritatively register artifact
        title = job.prompt or ("Infographic Poster" if art_type == ArtifactType.INFOGRAPHIC else "Video Briefing")
        
        if storage_service.file_exists(storage_ref):
            registered_artifact = artifact_service.register_artifact(
                title=title,
                artifact_type=art_type,
                file_format=file_ext,
                storage_ref=storage_ref,
                project_id=job.project_id,
                job_id=job.id,
                artifact_id=artifact_id,
                metadata={
                    "rendered_by": "github_actions" if payload.github_run_id else "turbo_worker",
                    "execution_id": payload.execution_id,
                    "github_run_id": payload.github_run_id,
                    "mime_type": payload.mime_type or ("video/mp4" if is_video else "image/png"),
                    "filename": default_filename,
                },
            )
        else:
            with get_connection() as conn:
                existing_art = ArtifactRepository.get_artifact(conn, artifact_id)
                if not existing_art:
                    registered_artifact = Artifact(
                        id=artifact_id,
                        title=title,
                        artifact_type=art_type,
                        file_format=file_ext,
                        storage_ref=storage_ref,
                        size_bytes=actual_size,
                        content_hash=worker_hash,
                        project_id=job.project_id,
                        job_id=job.id,
                        validation_status=ValidationStatus.VALID,
                        metadata={
                            "rendered_by": "github_actions" if payload.github_run_id else "turbo_worker",
                            "execution_id": payload.execution_id,
                            "github_run_id": payload.github_run_id,
                            "mime_type": payload.mime_type or ("video/mp4" if is_video else "image/png"),
                            "filename": default_filename,
                        },
                    )
                    ArtifactRepository.create_artifact(conn, registered_artifact)
                else:
                    registered_artifact = existing_art

        # 5. Transition job to COMPLETED atomically
        try:
            job_service.update_progress(
                job_id=job_id,
                state=JobState.COMPLETED,
                progress=1.0,
                current_stage="Deliverable rendered successfully",
                artifact_ids=[registered_artifact.id],
            )
        except InvalidStateError:
            pass

        # 6. Emit real-time SSE events exactly once
        try:
            event_broker.emit(
                job_id=job_id,
                event_type=TransformationEventType.ARTIFACT_CREATED,
                payload={
                    "artifact_id": registered_artifact.id,
                    "title": registered_artifact.title,
                    "storage_ref": registered_artifact.storage_ref,
                    "artifact_type": registered_artifact.artifact_type.value,
                    "file_format": registered_artifact.file_format,
                    "content_hash": registered_artifact.content_hash,
                    "size_bytes": registered_artifact.size_bytes,
                },
            )
            event_broker.emit(
                job_id=job_id,
                event_type=TransformationEventType.JOB_COMPLETED,
                payload={"artifact_ids": [registered_artifact.id]},
            )
        except Exception as ee:
            logger.warning("Failed to emit SSE completion event: %s", ee)

        return {
            "status": "completed",
            "job_id": job_id,
            "artifact_id": registered_artifact.id,
            "content_hash": registered_artifact.content_hash,
        }

    elif cb_status in ("failed", "error"):
        error_msg = payload.error_message or "Cloud render execution failed"
        try:
            job_service.update_progress(
                job_id=job_id,
                state=JobState.FAILED,
                progress=0.0,
                current_stage="Cloud render failed",
                error=error_msg,
            )
        except InvalidStateError:
            pass

        event_broker.emit(
            job_id=job_id,
            event_type=TransformationEventType.JOB_FAILED,
            payload={"error": error_msg},
        )
        return {"status": "failed", "job_id": job_id, "error": error_msg}

    elif cb_status in ("cancelled", "canceled"):
        try:
            job_service.update_progress(
                job_id=job_id,
                state=JobState.CANCELLED,
                progress=0.0,
                current_stage="Cloud render cancelled",
            )
        except InvalidStateError:
            pass

        event_broker.emit(
            job_id=job_id,
            event_type=TransformationEventType.JOB_CANCELLED,
            payload={"reason": "Cancelled by user or remote runner"},
        )
        return {"status": "cancelled", "job_id": job_id}

    return {"status": "unrecognized_status", "job_id": job_id}


@router.get("/{job_id}/stream")
async def stream_job_events(
    job_id: str,
    after_sequence: int = Query(0, ge=0, description="Resume event stream after sequence number"),
    last_event_id: Optional[str] = Header(None, alias="Last-Event-ID"),
    current_user: User = Depends(get_current_user),
):
    """Server-Sent Events (SSE) live progress and deliverable stream with durable replay."""
    job = job_service.get_job(job_id)
    authorize_resource(job.user_id, current_user)

    start_seq = after_sequence
    if last_event_id:
        try:
            start_seq = int(last_event_id)
        except ValueError:
            pass

    return StreamingResponse(
        event_broker.stream_job_events(job_id=job_id, after_sequence=start_seq),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{job_id}/canonical/{canonical_id}", response_model=CanonicalContent)
async def get_canonical_content(
    job_id: str,
    canonical_id: str,
    current_user: User = Depends(get_current_user),
) -> CanonicalContent:
    """Retrieve intermediate canonical content synthesized during a job."""
    job = job_service.get_job(job_id)
    authorize_resource(job.user_id, current_user)
    return job_service.get_canonical_content(canonical_id)
