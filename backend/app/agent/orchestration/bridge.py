"""LangGraph Orchestration Bridge managing background generation workflow dispatch."""

from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, Optional

from .models import WorkflowConfig, WorkflowStage, WorkflowState, WorkflowStatus

logger = logging.getLogger("limo.agent.orchestration")


class UnimplementedStageError(NotImplementedError):
    """Raised when dispatch reaches a pipeline stage not yet implemented in the current phase."""
    pass


class LangGraphBridge:
    """Deterministic orchestration bridge between Limo Agent and future workflow execution engines.
    
    Adheres strictly to MUST-FIX #3:
    Workflow requested -> configuration accepted -> dispatch to registered workflow.
    Fails explicitly when a pipeline stage (e.g. D5 Ingest, D6 Generate) has no real registered executor.
    Never uses fake or stub transformation pipelines.
    """

    def __init__(self):
        self._states: Dict[str, WorkflowState] = {}
        self._stage_handlers: Dict[WorkflowStage, Callable] = {}

    def register_stage_handler(self, stage: WorkflowStage, handler: Callable) -> None:
        """Register a real executor handler for a specific workflow stage."""
        self._stage_handlers[stage] = handler
        logger.info("Registered real handler for stage '%s'", stage.value)

    def is_stage_implemented(self, stage: WorkflowStage) -> bool:
        """Check if an executor handler has been registered for this stage."""
        return stage in self._stage_handlers

    def register_default_generation_handler(self, service: Optional[Any] = None) -> None:
        """Register the D6.4 orchestrator handler on WorkflowStage.GENERATE."""
        from ...services.transform_service import transform_service
        svc = service or transform_service

        def generation_handler(state: WorkflowState) -> Dict[str, Any]:
            result = svc.orchestrate_transformation(state.job_id)
            return result.model_dump(mode="json")

        self.register_stage_handler(WorkflowStage.GENERATE, generation_handler)

    def accept_configuration(self, config: WorkflowConfig) -> WorkflowState:
        """Accept and validate workflow configuration for background dispatch."""
        state = WorkflowState(
            job_id=config.job_id,
            status=WorkflowStatus.PENDING,
            stage_data={"config": config.model_dump()},
        )
        self._states[config.job_id] = state
        logger.info("Accepted workflow configuration for job '%s' (%d stages planned)", config.job_id, len(config.target_stages))
        return state

    def get_state(self, job_id: str) -> Optional[WorkflowState]:
        """Retrieve current runtime state for a workflow job."""
        return self._states.get(job_id)

    async def dispatch_next_stage(self, job_id: str) -> WorkflowState:
        """Execute next target stage or fail explicitly with UnimplementedStageError."""
        state = self._states.get(job_id)
        if not state:
            raise KeyError(f"Workflow job '{job_id}' not found")

        config_dict = state.stage_data.get("config", {})
        target_stages = [WorkflowStage(s) for s in config_dict.get("target_stages", [])]

        remaining = [s for s in target_stages if s not in state.completed_stages]
        if not remaining:
            state.status = WorkflowStatus.COMPLETED
            state.current_stage = None
            state.updated_at = datetime.now(timezone.utc)
            logger.info("Workflow job '%s' has completed all stages", job_id)
            return state

        next_stage = remaining[0]
        state.current_stage = next_stage
        state.status = WorkflowStatus.RUNNING

        # Explicit failure contract (MUST-FIX #3): No fake pipeline implementations!
        if not self.is_stage_implemented(next_stage):
            err_msg = (
                f"Workflow stage '{next_stage.value}' is not implemented in Phase D4.6. "
                f"Real execution requires Phase {self._get_phase_for_stage(next_stage)}."
            )
            state.status = WorkflowStatus.FAILED
            state.error = err_msg
            state.updated_at = datetime.now(timezone.utc)
            logger.error("Explicit dispatch failure: %s", err_msg)
            raise UnimplementedStageError(err_msg)

        handler = self._stage_handlers[next_stage]
        try:
            import inspect
            if inspect.iscoroutinefunction(handler):
                result = await handler(state)
            else:
                result = handler(state)

            state.completed_stages.append(next_stage)
            state.stage_data[next_stage.value] = result
            state.status = WorkflowStatus.STAGE_COMPLETED
            state.updated_at = datetime.now(timezone.utc)
            return state
        except Exception as e:
            state.status = WorkflowStatus.FAILED
            state.error = str(e)
            state.updated_at = datetime.now(timezone.utc)
            raise

    @staticmethod
    def _get_phase_for_stage(stage: WorkflowStage) -> str:
        """Return the target roadmap phase for an unbuilt stage."""
        mapping = {
            WorkflowStage.INGEST: "D5 (Content Ingestion)",
            WorkflowStage.CANONICAL: "D5 (Content Ingestion)",
            WorkflowStage.GENERATE: "D6 (Generation Engine) / D7 / D8",
            WorkflowStage.VALIDATE: "D11 (Provenance & Verification)",
            WorkflowStage.DELIVER: "D6 (Transformation & Generation)",
        }
        return mapping.get(stage, "Future Phase")
