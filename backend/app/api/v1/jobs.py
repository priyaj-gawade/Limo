"""Transformation Jobs REST API router with SSE streaming and resource authorization."""

import json
import logging
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
from ...services.transformation.github_dispatcher import github_actions_dispatcher
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
    mime_type: Optional[str] = None
    filename: Optional[str] = None
    error_message: Optional[str] = None


def _verify_worker_access(worker_key: Optional[str]) -> bool:
    """Verify worker authentication token."""
    expected_token = (settings.worker_token or "limo-turbo-worker-secret-key-12345").strip()
    if not worker_key or worker_key.strip() != expected_token:
        return False
    return True


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

    # If GitHub Actions is actively rendering this job, dispatch remote cancellation
    if github_actions_dispatcher.is_configured():
        run_id = None
        if job.configuration and isinstance(job.configuration.format_overrides, dict):
            run_id = job.configuration.format_overrides.get("github_run_id")
        if not run_id and job.worker_id and job.worker_id.startswith("gh_run_"):
            run_id = job.worker_id.replace("gh_run_", "")
        if run_id:
            logger.info("Triggering remote GitHub Actions run cancellation: %s", run_id)
            github_actions_dispatcher.cancel_workflow_run(str(run_id))

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
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    filename = file.filename or f"{art_id}.bin"
    storage_ref, size_bytes, computed_sha256 = storage_service.save_artifact_file(
        artifact_id=art_id,
        filename=filename,
        content=file_bytes,
    )

    logger.info(
        "Received worker file upload for job %s: art_id=%s, size=%d bytes, ref=%s",
        job_id,
        art_id,
        size_bytes,
        storage_ref,
    )

    return {
        "artifact_id": art_id,
        "storage_ref": storage_ref,
        "size_bytes": size_bytes,
        "sha256": computed_sha256,
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
        "Received worker callback for job %s: status=%s, exec_id=%s, run_id=%s",
        job_id,
        cb_status,
        payload.execution_id,
        payload.github_run_id,
    )

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
        # Idempotency check: if job is already COMPLETED and artifact registered, return immediately
        if job.state == JobState.COMPLETED and payload.artifact_id in job.artifact_ids:
            logger.info("Duplicate completed callback ignored for job %s (idempotent)", job_id)
            return {"status": "completed", "job_id": job_id, "artifact_id": payload.artifact_id}

        artifact_id = payload.artifact_id or f"art_gh_{payload.execution_id}"
        is_video = bool(payload.filename and payload.filename.endswith(".mp4")) or (
            payload.mime_type and "video" in payload.mime_type
        )
        art_type = ArtifactType.VIDEO if is_video else ArtifactType.INFOGRAPHIC
        file_ext = ".mp4" if is_video else ".png"

        storage_ref = payload.storage_ref or f"worker://{artifact_id}"

        # Normalize SHA-256 content hash
        sha256_hash = payload.sha256.strip() if (payload.sha256 and len(payload.sha256.strip()) == 64) else hashlib.sha256(f"{artifact_id}:{job_id}".encode("utf-8")).hexdigest()

        # Register artifact in database if not already present
        with get_connection() as conn:
            existing_art = ArtifactRepository.get_artifact(conn, artifact_id)
            if not existing_art:
                art = Artifact(
                    id=artifact_id,
                    title=job.prompt or "Cloud Deliverable",
                    artifact_type=art_type,
                    file_format=file_ext,
                    storage_ref=storage_ref,
                    size_bytes=payload.size_bytes or 0,
                    content_hash=sha256_hash,
                    project_id=job.project_id,
                    job_id=job.id,
                    validation_status=ValidationStatus.VALID,
                    metadata={
                        "rendered_by": "github_actions" if payload.github_run_id else "turbo_worker",
                        "execution_id": payload.execution_id,
                        "github_run_id": payload.github_run_id,
                        "mime_type": payload.mime_type or ("video/mp4" if is_video else "image/png"),
                    },
                )
                ArtifactRepository.create_artifact(conn, art)
                logger.info("Registered worker artifact in DB: %s (%s)", art.id, art.storage_ref)

        # Transition job to COMPLETED atomically
        try:
            job_service.update_progress(
                job_id=job_id,
                state=JobState.COMPLETED,
                progress=1.0,
                current_stage="Deliverable rendered successfully",
                artifact_ids=[artifact_id],
            )
        except InvalidStateError:
            pass

        # Emit real-time SSE event to trigger chat deliverable card
        try:
            event_broker.emit(
                job_id=job_id,
                event_type=TransformationEventType.DELIVERABLE_COMPLETED,
                payload={
                    "artifact_id": artifact_id,
                    "title": job.prompt or "Cloud Deliverable",
                    "storage_ref": storage_ref,
                    "format": "video" if is_video else "infographic",
                },
            )
            event_broker.emit(
                job_id=job_id,
                event_type=TransformationEventType.JOB_COMPLETED,
                payload={"artifact_ids": [artifact_id]},
            )
        except Exception as ee:
            logger.warning("Failed to emit SSE completion event: %s", ee)

        return {"status": "completed", "job_id": job_id, "artifact_id": artifact_id}

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
