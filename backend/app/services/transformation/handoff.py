"""Job and Artifact Handoff Service (Phase D6.5).

Connects D6.4 workflow results to persistent TransformationJob state, real Artifact records,
and ordered public lifecycle events:
- Synchronizes SQLite job state (COMPLETED, WAITING_EXTERNAL, PARTIALLY_COMPLETED, FAILED, CANCELLED).
- Links real completed artifacts bidirectionally (Job.artifact_ids <-> Artifact.job_id).
- Passively stages blocked external contracts for D7/D8 without auto-dispatch or worker polling.
- Calculates exact task-based progress (completed_tasks / total_tasks), decoupled from status.
- Emits atomic, monotonic lifecycle events from job.started onward (job.created owned by creation layer).
- Provides referential integrity validation between SQLite jobs and stored physical artifacts.
"""

import logging
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

from ...core.ids import generate_artifact_id
from ...exceptions import BadRequestError, EntityNotFoundError, StorageError
from ...models.artifact import Artifact
from ...models.enums import ArtifactType, JobState
from ...models.job import TransformationJob
from ...models.transformation_events import TransformationEventType
from ...models.workflow import TransformationWorkflowResult, WorkflowStatus
from ...services.artifact_service import ArtifactService, artifact_service
from ...services.job_service import JobService, job_service
from ...storage.service import StorageService, storage_service
from .event_broker import TransformationEventBroker, event_broker

logger = logging.getLogger("limo.services.transformation.handoff")


class JobArtifactHandoffService:
    """Orchestrates job state persistence, artifact linking, contract stashing, and event dispatch."""

    def __init__(
        self,
        job_svc: Optional[JobService] = None,
        art_svc: Optional[ArtifactService] = None,
        broker: Optional[TransformationEventBroker] = None,
        storage: Optional[StorageService] = None,
    ):
        self.job_svc = job_svc or job_service
        self.art_svc = art_svc or artifact_service
        self.event_broker = broker or event_broker
        self.storage = storage or storage_service

    def on_job_started(self, job_id: str) -> TransformationJob:
        """Mark job as PROCESSING and emit job.started lifecycle event."""
        job = self.job_svc.get_job(job_id)
        if job.state in (JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED):
            # Job is already in a terminal state (e.g. idempotent retry/re-execution);
            # avoid illegal transition back to PROCESSING or duplicate started event.
            return job

        updated = self.job_svc.update_progress(
            job_id=job.id,
            state=JobState.PROCESSING,
            progress=0.0,
            current_stage="Transformation workflow execution started",
        )
        self.event_broker.emit(
            job_id=job.id,
            event_type=TransformationEventType.JOB_STARTED,
            payload={
                "project_id": job.project_id,
                "session_id": job.session_id,
                "requested_formats": [f.value for f in job.requested_formats],
                "total_deliverables": len(job.requested_formats),
            },
        )
        return updated

    def on_task_started(
        self,
        job_id: str,
        deliverable_id: str,
        format_val: str,
        engine_type: str,
        attempt: int = 0,
    ) -> None:
        """Emit task.started event for a deliverable task."""
        self.event_broker.emit(
            job_id=job_id,
            event_type=TransformationEventType.TASK_STARTED,
            payload={
                "deliverable_id": deliverable_id,
                "format": format_val,
                "engine_type": engine_type,
                "attempt": attempt,
            },
        )

    def on_task_progress(
        self,
        job_id: str,
        deliverable_id: str,
        format_val: str,
        stage: str,
        message: str,
    ) -> None:
        """Emit task.progress lifecycle event for long-running deliverables (e.g. video)."""
        self.event_broker.emit(
            job_id=job_id,
            event_type=TransformationEventType.TASK_PROGRESS,
            payload={
                "deliverable_id": deliverable_id,
                "format": format_val,
                "stage": stage,
                "message": message,
            },
        )

    def on_task_completed(
        self,
        job_id: str,
        deliverable_id: str,
        format_val: str,
        artifact: Optional[Artifact] = None,
    ) -> None:
        """Emit task.completed event and artifact.created event when deliverable finishes."""
        self.event_broker.emit(
            job_id=job_id,
            event_type=TransformationEventType.TASK_COMPLETED,
            payload={
                "deliverable_id": deliverable_id,
                "format": format_val,
            },
        )
        if artifact:
            self.event_broker.emit(
                job_id=job_id,
                event_type=TransformationEventType.ARTIFACT_CREATED,
                payload={
                    "artifact_id": artifact.id,
                    "deliverable_id": deliverable_id,
                    "title": artifact.title,
                    "file_format": artifact.file_format,
                    "size_bytes": artifact.size_bytes,
                    "content_hash": artifact.content_hash,
                    "artifact_type": artifact.artifact_type.value,
                },
            )

    def on_task_failed(
        self,
        job_id: str,
        deliverable_id: str,
        format_val: str,
        error_msg: str,
    ) -> None:
        """Emit task.failed event with safe error string."""
        self.event_broker.emit(
            job_id=job_id,
            event_type=TransformationEventType.TASK_FAILED,
            payload={
                "deliverable_id": deliverable_id,
                "format": format_val,
                "error": error_msg,
            },
        )

    def handoff_workflow_result(
        self,
        job_id: str,
        result: TransformationWorkflowResult,
    ) -> Tuple[TransformationJob, TransformationWorkflowResult]:
        """Synchronize D6.4 result to persistent TransformationJob state, stage contracts, and emit terminal events.
        
        Strict adherence to Phase D6.5 principles:
        1. Progress = completed_deliverables / total_deliverables (real task ratio, decoupled from status).
        2. Status = independent lifecycle outcome (COMPLETED, WAITING_EXTERNAL, PARTIALLY_COMPLETED, FAILED, CANCELLED).
        3. Blocked contracts are passively stored in configuration.format_overrides["blocked_contracts"] (NO auto-dispatch).
        4. Artifact IDs are merged with deduplication.
        5. Emits corresponding terminal lifecycle event (job.completed, job.waiting_external, etc.).
        """
        job = self.job_svc.get_job(job_id)

        total_deliverables = max(1, result.total_deliverables)
        completed_count = len(result.completed_deliverable_ids)
        blocked_count = len(result.blocked_contracts)
        failed_count = len(result.failed_tasks)

        # 1. Calculate real progress: completed / total (MUST-FIX #5)
        raw_progress = completed_count / total_deliverables
        progress = round(min(1.0, max(0.0, raw_progress)), 3)

        # 2. Determine persistent JobState and Stage description
        if result.status == WorkflowStatus.COMPLETED:
            new_state = JobState.COMPLETED
            progress = 1.0
            stage = f"Completed all {result.total_deliverables} planned deliverables"
            terminal_event = TransformationEventType.JOB_COMPLETED

        elif result.status == WorkflowStatus.WAITING_EXTERNAL:
            new_state = JobState.WAITING_EXTERNAL
            progress = 0.0  # 0 native deliverables completed, strictly reflecting real tasks
            stage = f"All {result.total_deliverables} deliverables guarded for external execution (D7/D8)"
            terminal_event = TransformationEventType.JOB_WAITING_EXTERNAL

        elif result.status == WorkflowStatus.PARTIALLY_COMPLETED:
            new_state = JobState.PARTIALLY_COMPLETED
            stage = (
                f"Completed {completed_count} of {result.total_deliverables} deliverables "
                f"({blocked_count} external pending D7/D8"
                + (f", {failed_count} failed" if failed_count > 0 else "")
                + ")"
            )
            terminal_event = TransformationEventType.JOB_PARTIALLY_COMPLETED

        elif result.status == WorkflowStatus.CANCELLED:
            new_state = JobState.CANCELLED
            stage = f"Transformation workflow cancelled ({completed_count} completed, {total_deliverables - completed_count} skipped)"
            terminal_event = TransformationEventType.JOB_CANCELLED

        else:
            new_state = JobState.FAILED
            stage = f"Transformation workflow failed ({failed_count} tasks failed)"
            terminal_event = TransformationEventType.JOB_FAILED

        # 3. Construct safe user error string if any task failed
        error_str = None
        if result.failed_tasks:
            error_str = "; ".join(f"{t.get('format')}: {t.get('error')}" for t in result.failed_tasks)

        # 4. Passively stage blocked external contracts into format_overrides (MUST-FIX #4)
        if result.blocked_contracts:
            job.configuration.format_overrides["blocked_contracts"] = result.blocked_contracts

        # 5. Persist to SQLite via JobService (idempotent for already terminal jobs)
        artifact_ids_to_link = [a.id for a in result.artifacts]
        if job.state in (JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED) and job.state == new_state:
            updated_job = job
        else:
            updated_job = self.job_svc.update_progress(
                job_id=job.id,
                state=new_state,
                progress=progress,
                current_stage=stage,
                error=error_str,
                artifact_ids=artifact_ids_to_link,
                configuration=job.configuration,
            )

        logger.info(
            "Handoff completed for job '%s': state=%s, progress=%.3f, artifacts=%d, blocked_contracts=%d",
            job.id,
            new_state.value,
            progress,
            len(artifact_ids_to_link),
            blocked_count,
        )

        # 6. Emit terminal event
        self.event_broker.emit(
            job_id=job.id,
            event_type=terminal_event,
            payload={
                "state": new_state.value,
                "progress": progress,
                "current_stage": stage,
                "completed_count": completed_count,
                "blocked_count": blocked_count,
                "failed_count": failed_count,
                "total_deliverables": result.total_deliverables,
                "artifact_ids": updated_job.artifact_ids,
                "execution_time_seconds": result.execution_time_seconds,
            },
        )

        return updated_job, result

    def get_staged_contracts(self, job_id: str) -> Dict[str, Dict[str, Any]]:
        """Retrieve passively staged external contracts for D7/D8 without executing them."""
        job = self.job_svc.get_job(job_id)
        return job.configuration.format_overrides.get("blocked_contracts", {})

    def verify_job_artifact_linkage(self, job_id: str) -> bool:
        """Verify bidirectional referential integrity between job and its registered artifacts."""
        job = self.job_svc.get_job(job_id)
        artifacts = self.art_svc.list_artifacts(job_id=job_id)

        # 1. Assert job.artifact_ids matches list of artifacts linked to job_id
        job_art_set = set(job.artifact_ids)
        linked_art_set = {a.id for a in artifacts}
        if job_art_set != linked_art_set:
            logger.error(
                "Linkage mismatch for job '%s': job.artifact_ids=%s vs linked=%s",
                job_id,
                job_art_set,
                linked_art_set,
            )
            return False

        # 2. Assert physical storage integrity for every linked artifact
        for art in artifacts:
            if not self.storage.file_exists(art.storage_ref):
                logger.error("Artifact file missing on disk: %s (%s)", art.id, art.storage_ref)
                return False
            data = self.storage.read_file(art.storage_ref)
            if self.storage.compute_sha256(data) != art.content_hash:
                logger.error("Artifact content hash mismatch: %s", art.id)
                return False

        return True

    def handoff_genoffice_artifact(
        self,
        job_id: str,
        genoffice_job_id: str,
        genoffice_artifact: Dict[str, Any],
    ) -> Artifact:
        """Ingest a physical artifact from GenOffice automation into Limo sandboxed storage and register it.
        
        Strict compliance:
        1. Validates native file exists on disk and is readable.
        2. Computes content hash directly from bytes.
        3. Checks idempotency (prevents duplicate artifacts for same job + hash).
        4. Ingests bytes into sandboxed storage data/artifacts/art_<id>/.
        5. If thumbnail_path is provided and exists, ingests thumbnail into storage.
        6. Registers Artifact entity with metadata linking back to living native path.
        7. Links artifact ID into job.artifact_ids.
        8. Emits TransformationEventType.ARTIFACT_CREATED.
        """
        job = self.job_svc.get_job(job_id)

        file_path_str = genoffice_artifact.get("file_path") or ""
        file_path = Path(file_path_str)
        if not file_path_str or not file_path.is_file():
            raise StorageError(f"GenOffice artifact file does not exist on disk: '{file_path_str}'")

        file_bytes = file_path.read_bytes()
        content_hash = self.storage.compute_sha256(file_bytes)

        # Idempotency check: see if artifact already registered for this job with identical content hash
        existing_artifacts = self.art_svc.list_artifacts(job_id=job.id)
        for existing in existing_artifacts:
            if existing.content_hash == content_hash:
                logger.info(
                    "GenOffice artifact already ingested for job '%s' with hash '%s' (artifact_id: %s)",
                    job.id,
                    content_hash[:8],
                    existing.id,
                )
                return existing

        art_id = generate_artifact_id()
        filename = file_path.name
        storage_ref, size_bytes, _ = self.storage.save_artifact_file(
            artifact_id=art_id,
            filename=filename,
            content=file_bytes,
        )

        metadata = {
            "genoffice_file_path": str(file_path.resolve()),
            "genoffice_job_id": genoffice_job_id,
            "engine": "genoffice",
        }

        # Ingest thumbnail if present
        thumbnail_path_str = genoffice_artifact.get("thumbnail_path") or f"{file_path_str}.thumb.png"
        thumbnail_path = Path(thumbnail_path_str)
        if thumbnail_path.is_file():
            thumb_bytes = thumbnail_path.read_bytes()
            thumb_ref, _, _ = self.storage.save_artifact_file(
                artifact_id=art_id,
                filename="thumbnail.png",
                content=thumb_bytes,
            )
            metadata["thumbnail_storage_ref"] = thumb_ref

        # Classify artifact type
        ext = file_path.suffix.lower()
        if ext in (".docx", ".doc", ".pdf"):
            art_type = ArtifactType.DOC
        elif ext in (".xlsx", ".xls", ".csv"):
            art_type = ArtifactType.SHEET
        elif ext in (".pptx", ".ppt"):
            art_type = ArtifactType.SLIDE
        else:
            art_type = ArtifactType.DOC

        title = genoffice_artifact.get("title") or file_path.stem

        artifact = self.art_svc.register_artifact(
            title=title,
            artifact_type=art_type,
            file_format=ext,
            storage_ref=storage_ref,
            project_id=job.project_id,
            job_id=job.id,
            description=f"Generated {ext.upper()} document via GenOffice automation",
            metadata=metadata,
            artifact_id=art_id,
        )

        # Update job's artifact_ids
        art_ids = list(job.artifact_ids)
        if artifact.id not in art_ids:
            art_ids.append(artifact.id)
            self.job_svc.update_progress(
                job_id=job.id,
                state=job.state,
                progress=job.progress,
                current_stage=job.current_stage or "Artifact generated via GenOffice",
                artifact_ids=art_ids,
            )

        # Emit ARTIFACT_CREATED event
        self.event_broker.emit(
            job_id=job.id,
            event_type=TransformationEventType.ARTIFACT_CREATED,
            payload={
                "artifact_id": artifact.id,
                "job_id": job.id,
                "genoffice_job_id": genoffice_job_id,
                "title": artifact.title,
                "file_format": artifact.file_format,
                "size_bytes": artifact.size_bytes,
                "content_hash": artifact.content_hash,
                "artifact_type": artifact.artifact_type.value,
                "thumbnail_available": "thumbnail_storage_ref" in metadata,
            },
        )

        logger.info(
            "Successfully ingested and handed off GenOffice artifact '%s' for job '%s' (format: %s, bytes: %d)",
            artifact.id,
            job.id,
            artifact.file_format,
            size_bytes,
        )
        return artifact

    def handoff_video_artifact(
        self,
        job_id: str,
        deliverable_id: str,
        openmontage_result: Dict[str, Any],
        title: Optional[str] = None,
        canonical_id: Optional[str] = None,
        canonical_hash: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Artifact:
        """Ingest a physical MP4 artifact from OpenMontage runner into Limo sandboxed storage and register it.

        Strict compliance:
        1. Validates output file exists on disk, is non-empty, and ends with .mp4.
        2. Computes content hash directly from bytes.
        3. Checks idempotency (prevents duplicate artifacts for same job + hash).
        4. Ingests bytes into sandboxed storage data/artifacts/art_<id>/final.mp4.
        5. Registers Artifact entity with metadata linking back to OpenMontage output metadata.
        6. Links artifact ID into job.artifact_ids if job exists.
        7. Emits TransformationEventType.ARTIFACT_CREATED.
        """
        output_info = openmontage_result.get("output") or {}
        output_path_str = output_info.get("path") or ""
        output_path = Path(output_path_str)
        if not output_path_str or not output_path.is_file() or output_path.stat().st_size == 0:
            raise StorageError(f"OpenMontage video output file does not exist or is empty: '{output_path_str}'")

        if output_path.suffix.lower() != ".mp4":
            raise StorageError(f"Expected MP4 output from OpenMontage, got: '{output_path.name}'")

        file_bytes = output_path.read_bytes()
        content_hash = self.storage.compute_sha256(file_bytes)

        job = None
        if job_id:
            try:
                job = self.job_svc.get_job(job_id)
            except Exception:
                job = None

        # Idempotency check: reuse artifact if already registered for this job with identical hash
        if job:
            existing_artifacts = self.art_svc.list_artifacts(job_id=job.id)
            for existing in existing_artifacts:
                if existing.content_hash == content_hash:
                    logger.info(
                        "Video artifact already ingested for job '%s' with hash '%s' (artifact_id: %s)",
                        job.id,
                        content_hash[:8],
                        existing.id,
                    )
                    return existing

        art_id = generate_artifact_id()
        filename = output_info.get("filename") or output_path.name
        storage_ref, size_bytes, _ = self.storage.save_artifact_file(
            artifact_id=art_id,
            filename=filename,
            content=file_bytes,
        )

        runner_meta = openmontage_result.get("metadata") or {}
        metadata = {
            "deliverable_id": deliverable_id,
            "openmontage_job_id": openmontage_result.get("job_id"),
            "engine": "video_engine",
            "duration_seconds": output_info.get("duration_seconds", runner_meta.get("actual_duration_seconds")),
            "width": output_info.get("width"),
            "height": output_info.get("height"),
            "video_codec": output_info.get("video_codec"),
            "audio_codec": output_info.get("audio_codec"),
            "has_audio": output_info.get("has_audio", True),
            "tts_provider": runner_meta.get("tts_provider", "edge_tts"),
            "voice": runner_meta.get("voice", "en-US-AndrewMultilingualNeural"),
            "visual_provider": runner_meta.get("visual_provider", "auto"),
            "scene_count": runner_meta.get("scene_count", 2),
            "aspect_ratio": runner_meta.get("aspect_ratio", "16:9"),
            "render_runtime": runner_meta.get("render_runtime", "ffmpeg"),
        }
        if canonical_id:
            metadata["canonical_id"] = canonical_id
        if canonical_hash:
            metadata["canonical_hash"] = canonical_hash

        artifact_title = title or runner_meta.get("title") or output_path.stem
        dur_str = f"{metadata['duration_seconds']}s" if metadata.get("duration_seconds") else "video"
        res_str = f"{metadata['width']}x{metadata['height']}" if metadata.get("width") else "16:9"

        # Resilient multi-tier video poster extraction (0.5s -> min(0.1s, duration) -> 0.0s)
        try:
            dur_val = float(output_info.get("duration_seconds") or runner_meta.get("actual_duration_seconds") or 3.0)
            thumb_bytes = _extract_video_thumbnail(output_path, dur_val)
            if thumb_bytes:
                thumb_ref, _, _ = self.storage.save_artifact_file(
                    artifact_id=art_id,
                    filename="thumbnail.png",
                    content=thumb_bytes,
                )
                metadata["thumbnail_storage_ref"] = thumb_ref
        except Exception as ex:
            logger.warning("Could not extract poster thumbnail for video '%s': %s", art_id, ex)

        resolved_project_id = project_id or (job.project_id if job else None)
        resolved_job_id = job.id if job else None

        artifact = self.art_svc.register_artifact(
            title=artifact_title,
            artifact_type=ArtifactType.VIDEO,
            file_format=".mp4",
            storage_ref=storage_ref,
            project_id=resolved_project_id,
            job_id=resolved_job_id,
            description=f"Generated {metadata['aspect_ratio']} video ({dur_str}) via OpenMontage engine",
            stats=f"{dur_str} • {res_str}",
            metadata=metadata,
            artifact_id=art_id,
        )

        # Update job's artifact_ids if job exists
        if job:
            art_ids = list(job.artifact_ids)
            if artifact.id not in art_ids:
                art_ids.append(artifact.id)
                self.job_svc.update_progress(
                    job_id=job.id,
                    state=job.state,
                    progress=job.progress,
                    current_stage=job.current_stage or "Artifact generated via OpenMontage",
                    artifact_ids=art_ids,
                )

            # Emit ARTIFACT_CREATED event
            self.event_broker.emit(
                job_id=job.id,
                event_type=TransformationEventType.ARTIFACT_CREATED,
                payload={
                    "artifact_id": artifact.id,
                    "job_id": job.id,
                    "deliverable_id": deliverable_id,
                    "title": artifact.title,
                    "file_format": artifact.file_format,
                    "size_bytes": artifact.size_bytes,
                    "content_hash": artifact.content_hash,
                    "artifact_type": artifact.artifact_type.value,
                    "duration_seconds": metadata.get("duration_seconds"),
                    "resolution": f"{metadata.get('width')}x{metadata.get('height')}",
                },
            )

        logger.info(
            "Successfully ingested and handed off Video artifact '%s' for job '%s' (bytes: %d, sha256: %s)",
            artifact.id,
            resolved_job_id,
            size_bytes,
            content_hash[:8],
        )
        return artifact

    def handoff_image_artifact(
        self,
        job_id: Optional[str],
        deliverable_id: str,
        prismo_result: Dict[str, Any],
        title: Optional[str] = None,
        canonical_id: Optional[str] = None,
        canonical_hash: Optional[str] = None,
        project_id: Optional[str] = None,
        allowed_workspace_root: Optional[Path] = None,
    ) -> Artifact:
        """Ingest a physical PNG/JPEG artifact from Prismo runner into Limo sandboxed storage and register it.

        Strict Phase D8.8 Compliance:
        1. Validates output file path resolves strictly inside allowed_workspace_root (path containment).
        2. Validates output file exists, is non-empty, and bounded (1KB to 50MB).
        3. Validates binary image signatures (PNG magic bytes: \\x89PNG\\r\\n\\x1a\\n or JPEG SOI: \\xff\\xd8\\xff).
        4. Validates PNG IHDR chunk dimensions (width x height).
        5. Computes SHA-256 directly from file bytes.
        6. Idempotency check matching existing artifacts for this job.
        7. Saves to sandboxed storage: data/artifacts/art_<id>/final.png.
        8. Links thumbnail_storage_ref to artifact.storage_ref.
        9. Registers Artifact entity with ArtifactType.INFOGRAPHIC.
        10. Updates job artifact_ids if job exists and emits TransformationEventType.ARTIFACT_CREATED.
        """
        import struct

        export_info = prismo_result.get("export") or {}
        output_path_str = export_info.get("filePath") or ""
        if not output_path_str:
            raise StorageError("Missing export filePath in Prismo result")

        output_path = Path(output_path_str).resolve()

        # 1. Output Path Containment Security
        if allowed_workspace_root is not None:
            root = allowed_workspace_root.resolve()
            try:
                is_contained = output_path.is_relative_to(root)
            except AttributeError:
                is_contained = os.path.commonpath([str(root), str(output_path)]) == str(root)
            if not is_contained:
                raise StorageError(
                    f"Security violation: Runner output path '{output_path}' escapes allowed workspace root '{root}'"
                )

        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise StorageError(f"Prismo output file does not exist or is empty: '{output_path}'")

        file_bytes = output_path.read_bytes()
        size_bytes = len(file_bytes)

        # 2. Size bounds check (1 KB <= size <= 50 MB)
        if size_bytes < 1024 or size_bytes > 50 * 1024 * 1024:
            raise StorageError(f"Image size {size_bytes} bytes is out of valid bounds (1KB - 50MB)")

        # 3. Binary Magic Byte Validation
        is_png = file_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        is_jpeg = file_bytes.startswith(b"\xff\xd8\xff")
        if not is_png and not is_jpeg:
            raise StorageError("Output file failed binary image signature validation (not valid PNG/JPEG magic bytes)")

        # 4. PNG IHDR Chunk Dimension Extraction
        parsed_width = export_info.get("width", 1080)
        parsed_height = export_info.get("height", 1440)
        if is_png and len(file_bytes) >= 24:
            try:
                ihdr_w, ihdr_h = struct.unpack(">II", file_bytes[16:24])
                if ihdr_w > 0 and ihdr_h > 0:
                    parsed_width = ihdr_w
                    parsed_height = ihdr_h
            except Exception as ex:
                logger.warning("Could not parse IHDR dimensions from PNG: %s", ex)

        # 4b. Structural Decode Validation (full image structure, not just header)
        try:
            from PIL import Image
            import io

            img = Image.open(io.BytesIO(file_bytes))
            img.verify()  # Verify structure without full pixel decode
            # Re-open to get actual dimensions (verify() invalidates the object)
            img = Image.open(io.BytesIO(file_bytes))
            decoded_w, decoded_h = img.size
            if decoded_w != parsed_width or decoded_h != parsed_height:
                logger.warning(
                    "PIL dimensions (%dx%d) differ from IHDR (%dx%d), using PIL values",
                    decoded_w,
                    decoded_h,
                    parsed_width,
                    parsed_height,
                )
                parsed_width, parsed_height = decoded_w, decoded_h
        except ImportError:
            logger.warning("Pillow not available; skipping structural decode validation")
        except Exception as decode_err:
            raise StorageError(
                f"Image structural decode validation failed: {decode_err}. "
                "The file may be truncated or corrupted."
            )

        # 5. Cryptographic Checksum
        content_hash = self.storage.compute_sha256(file_bytes)

        job = None
        if job_id:
            try:
                job = self.job_svc.get_job(job_id)
            except Exception:
                job = None

        # 6. Idempotency check: reuse artifact if already registered for this job with identical hash
        if job:
            existing_artifacts = self.art_svc.list_artifacts(job_id=job.id)
            for existing in existing_artifacts:
                if existing.content_hash == content_hash:
                    logger.info(
                        "Image artifact already ingested for job '%s' with hash '%s' (artifact_id: %s)",
                        job.id,
                        content_hash[:8],
                        existing.id,
                    )
                    return existing

        # 7. Sandboxed Storage Ingestion
        art_id = generate_artifact_id()
        file_ext = ".jpg" if is_jpeg else ".png"
        filename = f"final{file_ext}"

        storage_ref, stored_size, _ = self.storage.save_artifact_file(
            artifact_id=art_id,
            filename=filename,
            content=file_bytes,
        )

        ratio_val = prismo_result.get("ratio") or "3:4"
        artifact_title = title or f"Poster_{art_id[:8]}"
        res_str = f"{parsed_width}x{parsed_height}"

        metadata = {
            "deliverable_id": deliverable_id,
            "engine": "prismo",
            "prismo_project_id": prismo_result.get("projectId"),
            "prismo_run_id": prismo_result.get("runId"),
            "aspect_ratio": ratio_val,
            "width": parsed_width,
            "height": parsed_height,
            "thumbnail_storage_ref": storage_ref,
            "diagnostics": prismo_result.get("diagnostics", {}),
        }
        if canonical_id:
            metadata["canonical_id"] = canonical_id
        if canonical_hash:
            metadata["canonical_hash"] = canonical_hash

        resolved_project_id = project_id or (job.project_id if job else None)
        resolved_job_id = job.id if job else None

        # 8. Register in SQLite via ArtifactService
        artifact = self.art_svc.register_artifact(
            title=artifact_title,
            artifact_type=ArtifactType.INFOGRAPHIC,
            file_format=file_ext,
            storage_ref=storage_ref,
            project_id=resolved_project_id,
            job_id=resolved_job_id,
            description=f"Generated {ratio_val} graphic poster deliverable via Prismo engine",
            stats=f"{res_str} • {ratio_val} Poster",
            metadata=metadata,
            artifact_id=art_id,
        )

        # 9. Update Job and Emit Event
        if job:
            art_ids = list(job.artifact_ids)
            if artifact.id not in art_ids:
                art_ids.append(artifact.id)
                self.job_svc.update_progress(
                    job_id=job.id,
                    state=job.state,
                    progress=job.progress,
                    current_stage=job.current_stage or "Poster generated via Prismo",
                    artifact_ids=art_ids,
                )

            self.event_broker.emit(
                job_id=job.id,
                event_type=TransformationEventType.ARTIFACT_CREATED,
                payload={
                    "artifact_id": artifact.id,
                    "job_id": job.id,
                    "deliverable_id": deliverable_id,
                    "title": artifact.title,
                    "file_format": artifact.file_format,
                    "size_bytes": artifact.size_bytes,
                    "content_hash": artifact.content_hash,
                    "artifact_type": artifact.artifact_type.value,
                    "aspect_ratio": ratio_val,
                    "resolution": res_str,
                },
            )

        logger.info(
            "Successfully ingested and handed off Prismo poster artifact '%s' for job '%s' (bytes: %d, sha256: %s, res: %s)",
            artifact.id,
            resolved_job_id,
            size_bytes,
            content_hash[:8],
            res_str,
        )
        return artifact


def _extract_video_thumbnail(output_path: Path, duration: float = 3.0) -> Optional[bytes]:
    """Resilient multi-tier poster frame extraction via ffmpeg:
    1. Try t=0.5s.
    2. Fallback to min(0.1s, max(0.01s, duration - 0.05s)).
    3. Fallback to first frame (0.0s).
    """
    attempts = [
        ["-ss", "00:00:00.500"],
        ["-ss", f"{max(0.01, min(0.1, duration - 0.05)):.3f}"],
        [],  # frame 0 fallback
    ]

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)

    try:
        for ss_args in attempts:
            cmd = ["ffmpeg", "-y"] + ss_args + ["-i", str(output_path), "-frames:v", "1", "-q:v", "2", str(tmp_path)]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if tmp_path.is_file() and tmp_path.stat().st_size > 0:
                    return tmp_path.read_bytes()
            except Exception:
                continue
    finally:
        if tmp_path.is_file():
            try:
                tmp_path.unlink()
            except Exception:
                pass
    return None


job_artifact_handoff_service = JobArtifactHandoffService()

