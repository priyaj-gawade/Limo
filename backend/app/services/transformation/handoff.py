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


job_artifact_handoff_service = JobArtifactHandoffService()
