"""Transform business service managing transformation contract creation, configuration resolution, and output planning."""

import logging
from typing import Any, List, Optional, Tuple

from ..db.connection import get_connection
from ..exceptions import BadRequestError, EntityNotFoundError, QueueFullError
from ..models.artifact import Artifact
from ..models.content import CanonicalContent
from ..models.enums import FeatureMode, JobState, OutputFormat
from ..models.job import GenerationConfig, TransformationJob
from ..models.transformation import OutputPlan, PlannedDeliverable, TransformationRequest
from ..services.chat_service import ChatService, chat_service
from ..services.job_service import JobService, job_service
from ..services.project_service import ProjectService, project_service
from ..services.source_service import SourceService, source_service
from ..models.workflow import TransformationWorkflowResult, WorkflowStatus
from ..services.transformation.config_resolver import (
    TransformationConfigResolver,
    transformation_config_resolver,
)
from ..services.transformation.engine_router import (
    EngineRouter,
    engine_router,
)
from ..services.transformation.output_planner import (
    OutputPlanner,
    output_planner,
)
from ..services.transformation.workflow_orchestrator import (
    TransformationWorkflowOrchestrator,
    workflow_orchestrator,
)
from ..services.transformation.handoff import (
    JobArtifactHandoffService,
    job_artifact_handoff_service,
)

logger = logging.getLogger("limo.services.transform")


class TransformService:
    """Business service for creating and managing transformation contracts."""

    def __init__(
        self,
        job_svc: Optional[JobService] = None,
        source_svc: Optional[SourceService] = None,
        proj_svc: Optional[ProjectService] = None,
        chat_svc: Optional[ChatService] = None,
        canonical_svc: Optional[Any] = None,
        config_resolver: Optional[TransformationConfigResolver] = None,
        planner: Optional[OutputPlanner] = None,
        router: Optional[EngineRouter] = None,
        orchestrator: Optional[TransformationWorkflowOrchestrator] = None,
        handoff_svc: Optional[JobArtifactHandoffService] = None,
    ):
        self.job_svc = job_svc or job_service
        self.source_svc = source_svc or source_service
        self.proj_svc = proj_svc or project_service
        self.chat_svc = chat_svc or chat_service
        self._canonical_svc = canonical_svc
        self.config_resolver = config_resolver or transformation_config_resolver
        self.planner = planner or output_planner
        self.engine_router = router or engine_router
        self.orchestrator = orchestrator or workflow_orchestrator
        self.handoff_svc = handoff_svc or job_artifact_handoff_service

    @property
    def canonical_svc(self) -> Any:
        if self._canonical_svc is None:
            from ..services.canonical.service import canonical_service
            self._canonical_svc = canonical_service
        return self._canonical_svc

    def create_transform_contract(
        self,
        requested_formats: List[OutputFormat],
        source_ids: Optional[List[str]] = None,
        prompt: Optional[str] = None,
        inline_content: Optional[str] = None,
        configuration: Optional[GenerationConfig] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        canonical_id: Optional[str] = None,
        feature_mode: Optional[FeatureMode] = None,
        user_id: Optional[str] = None,
    ) -> TransformationJob:
        """Validate inputs, resolve D6.1 configuration and D6.2 plan, and persist contract.

        Rules:
        - At least one input (source_ids, prompt, inline_content, or canonical_id) is required.
        - All referenced sources, project, and session must physically exist in SQLite.
        - If inline_content is supplied, it is registered as an ingested text source asset.
        - Reconciles D6.1 configuration and builds D6.2 OutputPlan when CanonicalContent is available.
        - Pure contract persistence: state is QUEUED. Zero fake generation.
        """
        clean_source_ids = list(source_ids or [])
        clean_prompt = prompt.strip() if prompt else None
        clean_inline = inline_content.strip() if inline_content else None

        if not clean_source_ids and not clean_prompt and not clean_inline and not canonical_id:
            raise BadRequestError(
                "At least one input source, prompt, inline content, or canonical ID must be provided"
            )

        if not requested_formats and not feature_mode:
            raise BadRequestError("At least one target OutputFormat or FeatureMode is required")

        # Verify parent entities if specified
        if project_id:
            self.proj_svc.get_project(project_id)

        if session_id:
            self.chat_svc.get_session(session_id)

        # Ingest inline content as a real text source if provided
        if clean_inline:
            source_title = f"Prompt Input ({clean_prompt[:30]}...)" if clean_prompt else "Inline Input Source"
            text_source = self.source_svc.register_text_source(
                name=source_title,
                text_content=clean_inline,
                project_id=project_id,
                metadata={"origin": "transform_inline_content"},
            )
            clean_source_ids.append(text_source.id)

        # Verify all referenced sources physically exist
        for src_id in clean_source_ids:
            self.source_svc.get_source(src_id)

        # Check for associated CanonicalContent
        canonical: Optional[CanonicalContent] = None
        if canonical_id:
            canonical = self.job_svc.get_canonical_content(canonical_id)
        elif clean_source_ids:
            canonical = self.canonical_svc.get_canonical_by_source_id(clean_source_ids[0])

        effective_config = configuration.model_copy() if configuration else GenerationConfig()
        effective_formats = list(requested_formats) if requested_formats else []

        # If CanonicalContent exists, apply D6.1 reconciliation and D6.2 output planning
        if canonical:
            request = self.config_resolver.resolve(
                canonical=canonical,
                structured_overrides=configuration,
                requested_formats=requested_formats,
                active_mode=feature_mode,
                user_prompt=clean_prompt,
                project_id=project_id,
                session_id=session_id,
            )
            plan = self.planner.plan(request=request, canonical_title=canonical.title)
            effective_config = request.config.model_copy()
            effective_config.format_overrides["output_plan"] = plan.model_dump(mode="json")
            effective_config.format_overrides["transformation_request"] = request.model_dump(mode="json")
            effective_formats = request.requested_formats

        # 1. Queue capacity check upfront: if queue is full, immediately reject with 429 without persisting to DB
        from .job_queue import job_queue_manager
        if job_queue_manager.is_running() and job_queue_manager.is_full():
            raise QueueFullError("Transformation worker queue is at capacity. Please retry shortly.")

        # 2. Persist to SQLite
        job = self.job_svc.create_job(
            requested_formats=effective_formats,
            configuration=effective_config,
            project_id=project_id,
            session_id=session_id,
            prompt=clean_prompt,
            source_ids=clean_source_ids,
            user_id=user_id,
        )

        # 3. Enqueue to worker if executable (has planned manifest); if enqueue fails, roll back newly created DB record
        has_plan = bool(effective_config.format_overrides.get("output_plan"))
        if job_queue_manager.is_running() and has_plan:
            try:
                job_queue_manager.enqueue(job.id)
            except Exception as e:
                try:
                    with get_connection(self.job_svc.db_path) as conn:
                        conn.execute("DELETE FROM jobs WHERE id = ?", (job.id,))
                except Exception:
                    pass
                logger.error("Could not enqueue job '%s' to worker queue, rolled back DB record: %s", job.id, e)
                raise

        logger.info(
            "Created transform contract '%s' (formats: %s, sources: %d, has_prompt: %s, has_canonical: %s)",
            job.id,
            [f.value for f in effective_formats],
            len(clean_source_ids),
            bool(clean_prompt),
            bool(canonical),
        )
        return job

    def plan_transformation(
        self,
        canonical_id: str,
        requested_formats: Optional[List[OutputFormat]] = None,
        configuration: Optional[GenerationConfig] = None,
        feature_mode: Optional[FeatureMode] = None,
        user_prompt: Optional[str] = None,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Tuple[TransformationRequest, OutputPlan]:
        """Directly resolve transformation configuration and output plan for a CanonicalContent."""
        canonical = self.job_svc.get_canonical_content(canonical_id)
        request = self.config_resolver.resolve(
            canonical=canonical,
            structured_overrides=configuration,
            requested_formats=requested_formats,
            active_mode=feature_mode,
            user_prompt=user_prompt,
            project_id=project_id,
            session_id=session_id,
        )
        plan = self.planner.plan(request=request, canonical_title=canonical.title)
        return request, plan

    def _get_job_plan(self, job: TransformationJob) -> OutputPlan:
        """Extract and validate the planned output manifest from a job."""
        plan_dict = job.configuration.format_overrides.get("output_plan")
        if not plan_dict:
            raise BadRequestError(f"Job '{job.id}' does not contain a planned output manifest")
        return OutputPlan.model_validate(plan_dict)

    def orchestrate_transformation(self, job_id: str) -> TransformationWorkflowResult:
        """Authoritative execution entry point orchestrating a TransformationJob workflow (Phase D6.4/D6.5)."""
        job = self.job_svc.get_job(job_id)

        # 1. Mark job as started and emit job.started
        self.handoff_svc.on_job_started(job.id)

        # 2. Execute workflow with live task lifecycle event reporting
        result = self.orchestrator.execute_job_workflow(job, handoff_svc=self.handoff_svc)

        # 3. Synchronize persistent job state, link artifacts, stage contracts, and emit terminal event
        self.handoff_svc.handoff_workflow_result(job.id, result)
        return result

    def execute_deliverable(self, deliverable_id: str, job_id: str) -> Artifact:
        """Execute a single planned deliverable delegating to the orchestrator (single execution path)."""
        artifact = self.orchestrator.execute_single_task(job_id=job_id, deliverable_id=deliverable_id)
        job = self.job_svc.get_job(job_id)
        plan = self._get_job_plan(job)
        art_ids = list(dict.fromkeys(job.artifact_ids + [artifact.id]))
        done = len(art_ids) == len(plan.deliverables)
        self.job_svc.update_progress(
            job_id=job.id,
            state=JobState.COMPLETED if done else JobState.PROCESSING,
            progress=round(len(art_ids) / max(1, len(plan.deliverables)), 3),
            current_stage=f"Generated {artifact.file_format} deliverable",
            artifact_ids=art_ids,
        )
        return artifact

    def get_transform_contract(self, job_id: str) -> TransformationJob:
        """Retrieve transformation contract status, deliverables, and progress."""
        return self.job_svc.get_job(job_id)

    def list_transform_contracts(
        self,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> List[TransformationJob]:
        """List transformation contracts ordered by creation timestamp."""
        return self.job_svc.list_jobs(project_id=project_id, session_id=session_id)


transform_service = TransformService()

