"""Transformation job lifecycle and contract business service."""

import logging
from typing import Any, List, Optional

from ..db.connection import get_connection
from ..db.repositories.job_repo import JobRepository
from ..db.repositories.project_repo import ProjectRepository
from ..exceptions import BadRequestError, EntityNotFoundError, InvalidStateError
from ..models.content import CanonicalContent
from ..models.enums import JobState, OutputFormat
from ..models.job import GenerationConfig, TransformationJob
from ..models.transformation_events import TransformationEventType

logger = logging.getLogger("limo.services.job")

TERMINAL_JOB_STATES = {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}


class JobService:
    """Business service managing transformation jobs and canonical content persistence."""

    def __init__(self, db_path: Optional[str] = None, event_broker: Optional[Any] = None):
        self.db_path = db_path
        self.event_broker = event_broker

    def create_job(
        self,
        requested_formats: List[OutputFormat],
        configuration: Optional[GenerationConfig] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        prompt: Optional[str] = None,
        source_ids: Optional[List[str]] = None,
        user_id: Optional[str] = None,
    ) -> TransformationJob:
        """Create and persist an execution contract for a multi-deliverable transformation request."""
        if not requested_formats:
            raise BadRequestError("At least one target OutputFormat is required")

        with get_connection(self.db_path) as conn:
            if project_id:
                project = ProjectRepository.get_project(conn, project_id)
                if not project:
                    raise EntityNotFoundError("Project", project_id)

            job = TransformationJob(
                user_id=user_id,
                project_id=project_id,
                session_id=session_id,
                prompt=prompt.strip() if prompt else None,
                source_ids=source_ids or [],
                requested_formats=requested_formats,
                configuration=configuration or GenerationConfig(),
                state=JobState.QUEUED,
                progress=0.0,
                current_stage="Queued for execution",
            )
            created = JobRepository.create_job(conn, job)
            logger.info("Created transformation job '%s' (%d formats, %d sources)", created.id, len(requested_formats), len(job.source_ids))

        # Emit job.created event outside the connection context so SQLite write lock is released
        try:
            broker = self.event_broker
            if broker is None:
                from .transformation.event_broker import event_broker as default_broker
                broker = default_broker
            broker.emit(
                job_id=created.id,
                event_type=TransformationEventType.JOB_CREATED,
                payload={
                    "project_id": created.project_id,
                    "session_id": created.session_id,
                    "requested_formats": [f.value for f in created.requested_formats],
                    "source_count": len(created.source_ids),
                },
            )
        except Exception as e:
            logger.warning("Failed to emit job.created event: %s", str(e))

        return created


    def get_job(self, job_id: str) -> TransformationJob:
        """Retrieve a job by ID or raise EntityNotFoundError."""
        with get_connection(self.db_path) as conn:
            job = JobRepository.get_job(conn, job_id)
            if not job:
                raise EntityNotFoundError("TransformationJob", job_id)
            return job

    def list_jobs(
        self,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        state: Optional[JobState] = None,
        user_id: Optional[str] = None,
    ) -> List[TransformationJob]:
        """List transformation jobs with optional filters, ordered by created_at DESC."""
        with get_connection(self.db_path) as conn:
            return JobRepository.list_jobs(
                conn,
                project_id=project_id,
                session_id=session_id,
                state=state,
                user_id=user_id,
            )

    def update_progress(
        self,
        job_id: str,
        state: JobState,
        progress: float,
        current_stage: Optional[str] = None,
        error: Optional[str] = None,
        artifact_ids: Optional[List[str]] = None,
        configuration: Optional[GenerationConfig] = None,
    ) -> TransformationJob:
        """Update job progress and state while enforcing terminal state protections."""
        if not (0.0 <= progress <= 1.0):
            raise BadRequestError(f"Progress must be between 0.0 and 1.0, got {progress}")

        # If completed, normalize progress to 1.0
        if state == JobState.COMPLETED:
            progress = 1.0

        with get_connection(self.db_path) as conn:
            job = JobRepository.get_job(conn, job_id)
            if not job:
                raise EntityNotFoundError("TransformationJob", job_id)

            if job.state in TERMINAL_JOB_STATES:
                raise InvalidStateError(
                    f"Cannot update job '{job_id}' in terminal state '{job.state.value}'"
                )

            # Preserve existing artifacts if not specified, or merge new ones
            merged_artifacts = None
            if artifact_ids is not None:
                # Merge unique IDs maintaining order
                seen = set(job.artifact_ids)
                merged = list(job.artifact_ids)
                for art_id in artifact_ids:
                    if art_id not in seen:
                        seen.add(art_id)
                        merged.append(art_id)
                merged_artifacts = merged

            success = JobRepository.update_job_progress(
                conn,
                job_id=job_id,
                state=state,
                progress=progress,
                current_stage=current_stage,
                error=error,
                artifact_ids=merged_artifacts,
                configuration=configuration,
            )
            if not success:
                raise EntityNotFoundError("TransformationJob", job_id)

            updated = JobRepository.get_job(conn, job_id)
            logger.info(
                "Updated job '%s' progress: state=%s, progress=%.2f, stage='%s'",
                job_id,
                state.value,
                progress,
                current_stage or "",
            )
            return updated  # type: ignore[return-value]

    def cancel_job(self, job_id: str) -> TransformationJob:
        """Cancel an active or queued job. Rejects cancellation of terminal jobs."""
        with get_connection(self.db_path) as conn:
            job = JobRepository.get_job(conn, job_id)
            if not job:
                raise EntityNotFoundError("TransformationJob", job_id)

            if job.state in TERMINAL_JOB_STATES:
                raise InvalidStateError(
                    f"Cannot cancel job '{job_id}' in terminal state '{job.state.value}'"
                )

            # Check if active worker is executing this job
            is_actively_running = False
            try:
                from .job_queue import job_queue_manager
                is_actively_running = job_queue_manager.is_job_active(job_id)
            except Exception:
                pass

            if is_actively_running:
                # Running by active worker: request cooperative cancellation and let worker halt cleanly at task boundary
                JobRepository.request_cancellation(conn, job_id)
                try:
                    job_queue_manager.request_cancellation(job_id)
                except Exception as ex:
                    logger.debug("Could not signal in-memory queue manager: %s", ex)
                logger.info("Requested cooperative cancellation for running job '%s'", job_id)
            else:
                # Queued or unmanaged processing job (e.g. tests or abandoned): transition directly to CANCELLED
                JobRepository.update_job_progress(
                    conn,
                    job_id=job_id,
                    state=JobState.CANCELLED,
                    progress=job.progress,
                    current_stage="Job cancelled by user",
                    error=None,
                    cancellation_requested=True,
                )
                logger.info("Cancelled non-running job '%s'", job_id)

            return JobRepository.get_job(conn, job_id)  # type: ignore[return-value]

    def save_canonical_content(self, canonical: CanonicalContent) -> CanonicalContent:
        """Persist intermediate structured CanonicalContent representation."""
        with get_connection(self.db_path) as conn:
            saved = JobRepository.save_canonical_content(conn, canonical)
            logger.info("Saved canonical content '%s' (hash: %s)", saved.id, saved.content_hash[:8])
            return saved

    def get_canonical_content(self, canonical_id: str) -> CanonicalContent:
        """Retrieve canonical content intermediate by ID or raise EntityNotFoundError."""
        with get_connection(self.db_path) as conn:
            canonical = JobRepository.get_canonical_content(conn, canonical_id)
            if not canonical:
                raise EntityNotFoundError("CanonicalContent", canonical_id)
            return canonical


job_service = JobService()
