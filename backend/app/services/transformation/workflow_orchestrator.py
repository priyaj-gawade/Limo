"""Transformation Workflow Orchestrator (Phase D6.4).

Coordinates the transformation workflow after D6.1/D6.2 planning and D6.3 contracts/adapters:
- Converts OutputPlan into executable DeliverableTask units.
- Enforces independent CanonicalContent execution (no artificial DAG dependencies).
- Dispatches native formats to D6.3 deterministic adapters (real files + SHA-256 integrity).
- Constructs versioned D6.3 contract payloads for external engines (guarded without fake execution).
- Enforces retry idempotency keyed by (job_id, deliverable_id).
- Supports task-boundary cancellation (active task finishes, pending tasks skipped).
- Exposes safe user-facing error messages on tasks without leaking internal tracebacks.
- Produces frozen TransformationWorkflowResult models for downstream D6.5 handoff.
"""

from datetime import datetime, timezone
import logging
import time
from typing import Any, Dict, List, Optional, Set

from ...core.ids import generate_task_id, generate_workflow_id
from ...exceptions import BadRequestError, EntityNotFoundError
from ...models.artifact import Artifact
from ...models.content import CanonicalContent
from ...models.enums import JobState, OutputFormat
from ...models.generation_config import GenerationConfig
from ...models.job import TransformationJob
from ...models.transformation import OutputPlan, PlannedDeliverable
from ...models.workflow import (
    DeliverableTask,
    TaskStatus,
    TransformationWorkflow,
    TransformationWorkflowResult,
    WorkflowStatus,
)
from ...services.artifact_service import ArtifactService, artifact_service
from ...services.job_service import JobService, job_service
from ...storage.service import StorageService, storage_service
from .contracts import GenerationContractBuilder, generation_contract_builder
from .engine_router import EngineRouter, engine_router

logger = logging.getLogger("limo.services.transformation.orchestrator")


class TransformationWorkflowOrchestrator:
    """Coordinates deliverable-level task execution across native adapters and external contracts."""

    def __init__(
        self,
        router: Optional[EngineRouter] = None,
        contract_bld: Optional[GenerationContractBuilder] = None,
        art_service: Optional[ArtifactService] = None,
        store_service: Optional[StorageService] = None,
        jb_service: Optional[JobService] = None,
    ):
        self.engine_router = router or engine_router
        self.contract_builder = contract_bld or generation_contract_builder
        self.artifact_svc = art_service or artifact_service
        self.storage_svc = store_service or storage_service
        self.job_svc = jb_service or job_service
        self._cancelled_workflows: Set[str] = set()

    def build_workflow(self, plan: OutputPlan, job_id: str) -> TransformationWorkflow:
        """Construct an executable TransformationWorkflow from an OutputPlan.
        
        All deliverables execute as independent siblings derived directly from CanonicalContent.
        """
        tasks: Dict[str, DeliverableTask] = {}
        task_order: List[str] = []

        for deliv in plan.deliverables:
            task = DeliverableTask(
                task_id=generate_task_id(),
                deliverable_id=deliv.deliverable_id,
                format=deliv.format,
                engine_type=deliv.route.engine_type,
                is_implemented=deliv.route.is_implemented,
                status=TaskStatus.PENDING,
            )
            tasks[deliv.deliverable_id] = task
            task_order.append(deliv.deliverable_id)

        workflow = TransformationWorkflow(
            id=generate_workflow_id(),
            job_id=job_id,
            plan_id=plan.id,
            canonical_id=plan.canonical_id,
            status=WorkflowStatus.PENDING,
            tasks=tasks,
            task_order=task_order,
        )

        logger.info(
            "Built transformation workflow '%s' for job '%s' with %d deliverables",
            workflow.id,
            job_id,
            len(task_order),
        )
        return workflow

    def cancel_workflow(self, workflow_id: str) -> bool:
        """Register cooperative cancellation signal for a workflow at task boundary."""
        self._cancelled_workflows.add(workflow_id)
        logger.info("Cancellation requested for transformation workflow '%s'", workflow_id)
        return True

    def is_cancelled(self, workflow_id: str, job_id: Optional[str] = None) -> bool:
        """Check if cancellation has been requested for this workflow or parent job."""
        if workflow_id in self._cancelled_workflows:
            return True
        if job_id:
            try:
                from ..job_queue import job_queue_manager
                if job_queue_manager.is_cancellation_requested(job_id):
                    return True
            except Exception:
                pass
        return False

    def execute_workflow(
        self,
        workflow: TransformationWorkflow,
        plan: OutputPlan,
        canonical: CanonicalContent,
        config: GenerationConfig,
        project_id: Optional[str] = None,
        max_retries: int = 2,
        handoff_svc: Optional[Any] = None,
    ) -> TransformationWorkflowResult:
        """Execute the planned tasks within a transformation workflow.
        
        Adheres strictly to Phase D6.4/D6.5 core principles:
        1. Direct CanonicalContent execution: tasks are independent siblings.
        2. Native execution: D6.3 adapters generate real files and real artifacts.
        3. External guarding: D7/D8 engines have typed contracts built and held as BLOCKED.
        4. Retry idempotency: Keyed by (job_id, deliverable_id).
        5. Task-boundary cancellation: Active task finishes cleanly, pending tasks skipped.
        6. Safe error strings on tasks without leaking internal tracebacks.
        7. Live task lifecycle reporting to handoff_svc if provided.
        """
        start_time = time.time()
        workflow.status = WorkflowStatus.RUNNING
        workflow.updated_at = datetime.now(timezone.utc)

        deliverables_by_id: Dict[str, PlannedDeliverable] = {
            d.deliverable_id: d for d in plan.deliverables
        }

        artifacts: List[Artifact] = []
        blocked_contracts: Dict[str, Dict[str, Any]] = {}
        failed_tasks: List[Dict[str, str]] = []
        completed_deliverable_ids: List[str] = []

        for deliv_id in workflow.task_order:
            task = workflow.tasks[deliv_id]
            deliverable = deliverables_by_id.get(deliv_id)
            if not deliverable:
                continue

            # Check task-boundary cancellation: Active tasks may finish cleanly,
            # but pending tasks become SKIPPED, explicitly preventing newly starting tasks after cancellation.
            if self.is_cancelled(workflow.id, job_id=workflow.job_id):
                logger.info(
                    "Workflow '%s' cancelled: skipping deliverable '%s' before task start",
                    workflow.id,
                    deliv_id,
                )
                task.status = TaskStatus.SKIPPED
                task.error = "Execution cancelled prior to task start"
                task.completed_at = datetime.now(timezone.utc)
                continue

            # ------------------------------------------------------------------
            # Branch A: Native Adapters (Implemented in D6.3)
            # ------------------------------------------------------------------
            if task.is_implemented:
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now(timezone.utc)
                if handoff_svc:
                    handoff_svc.on_task_started(
                        workflow.job_id,
                        deliv_id,
                        deliverable.format.value,
                        task.engine_type.value,
                        0,
                    )

                # Retry loop with strict idempotency
                attempt = 0
                success = False

                while attempt <= max_retries and not success:
                    task.retry_count = attempt
                    if self.is_cancelled(workflow.id, job_id=workflow.job_id):
                        task.status = TaskStatus.SKIPPED
                        task.error = "Execution cancelled prior to task retry"
                        task.completed_at = datetime.now(timezone.utc)
                        break
                    try:
                        if handoff_svc and attempt > 0:
                            handoff_svc.on_task_started(
                                workflow.job_id,
                                deliv_id,
                                deliverable.format.value,
                                task.engine_type.value,
                                attempt,
                            )

                        # Idempotency check: Reuse existing valid artifact if present
                        existing_artifact = self._find_existing_artifact(
                            job_id=workflow.job_id,
                            deliverable_id=deliv_id,
                        )
                        if existing_artifact:
                            logger.info(
                                "Idempotent hit: Reusing existing artifact '%s' for job '%s', deliverable '%s'",
                                existing_artifact.id,
                                workflow.job_id,
                                deliv_id,
                            )
                            art = existing_artifact
                        else:
                            art = self.engine_router.dispatch(
                                route=deliverable.route,
                                deliverable=deliverable,
                                canonical=canonical,
                                config=config,
                                project_id=project_id,
                                job_id=workflow.job_id,
                            )

                        if not art:
                            raise ValueError(f"Adapter dispatch returned empty artifact for {deliv_id}")

                        task.artifact_id = art.id
                        task.status = TaskStatus.COMPLETED
                        task.completed_at = datetime.now(timezone.utc)
                        artifacts.append(art)
                        completed_deliverable_ids.append(deliv_id)
                        success = True
                        if handoff_svc:
                            handoff_svc.on_task_completed(
                                workflow.job_id,
                                deliv_id,
                                deliverable.format.value,
                                art,
                            )

                    except Exception as e:
                        logger.exception(
                            "Transient failure executing native deliverable '%s' on attempt %d: %s",
                            deliv_id,
                            attempt,
                            str(e),
                        )
                        attempt += 1
                        if attempt > max_retries:
                            task.status = TaskStatus.FAILED
                            safe_msg = self._sanitize_error(e, deliverable.format)
                            task.error = safe_msg
                            task.completed_at = datetime.now(timezone.utc)
                            failed_tasks.append({
                                "deliverable_id": deliv_id,
                                "format": deliverable.format.value,
                                "error": safe_msg,
                            })
                            if handoff_svc:
                                handoff_svc.on_task_failed(
                                    workflow.job_id,
                                    deliv_id,
                                    deliverable.format.value,
                                    safe_msg,
                                )

            # ------------------------------------------------------------------
            # Branch B: External Engines (Guarded for D7 / D8)
            # ------------------------------------------------------------------
            else:
                task.status = TaskStatus.RUNNING
                task.started_at = datetime.now(timezone.utc)
                if handoff_svc:
                    handoff_svc.on_task_started(
                        workflow.job_id,
                        deliv_id,
                        deliverable.format.value,
                        task.engine_type.value,
                        0,
                    )

                # Prepare typed contract payload via EngineRouter and D6.3 contract builder
                try:
                    payload = self.engine_router.build_contract(
                        deliverable=deliverable,
                        canonical=canonical,
                        config=config,
                        project_id=project_id,
                        session_id=None,
                    )
                    payload_dict = (
                        payload.model_dump(mode="json")
                        if hasattr(payload, "model_dump")
                        else payload
                    )
                    task.contract_payload = payload_dict
                    task.status = TaskStatus.BLOCKED
                    task.error = (
                        f"Execution engine '{task.engine_type.value}' is guarded pending "
                        f"Phase {deliverable.route.target_phase}. Zero simulated outputs generated."
                    )
                    task.completed_at = datetime.now(timezone.utc)
                    blocked_contracts[deliv_id] = payload_dict
                    if handoff_svc:
                        handoff_svc.on_task_completed(
                            workflow.job_id,
                            deliv_id,
                            deliverable.format.value,
                            None,
                        )

                except Exception as e:
                    logger.exception("Failed to build contract payload for external deliverable '%s'", deliv_id)
                    task.status = TaskStatus.FAILED
                    safe_msg = f"Failed to construct {deliverable.format.value} contract payload"
                    task.error = safe_msg
                    task.completed_at = datetime.now(timezone.utc)
                    failed_tasks.append({
                        "deliverable_id": deliv_id,
                        "format": deliverable.format.value,
                        "error": safe_msg,
                    })
                    if handoff_svc:
                        handoff_svc.on_task_failed(
                            workflow.job_id,
                            deliv_id,
                            deliverable.format.value,
                            safe_msg,
                        )

        # ----------------------------------------------------------------------
        # Determine Overall Workflow Status
        # ----------------------------------------------------------------------
        total_count = len(workflow.tasks)
        completed_count = len(completed_deliverable_ids)
        blocked_count = len(blocked_contracts)
        failed_count = len(failed_tasks)

        if self.is_cancelled(workflow.id):
            final_status = WorkflowStatus.CANCELLED
        elif completed_count == total_count:
            final_status = WorkflowStatus.COMPLETED
        elif blocked_count == total_count:
            final_status = WorkflowStatus.WAITING_EXTERNAL
        elif failed_count == total_count:
            final_status = WorkflowStatus.FAILED
        elif completed_count > 0:
            final_status = WorkflowStatus.PARTIALLY_COMPLETED
        elif blocked_count > 0 and failed_count > 0:
            final_status = WorkflowStatus.PARTIALLY_COMPLETED
        else:
            final_status = WorkflowStatus.FAILED

        workflow.status = final_status
        workflow.updated_at = datetime.now(timezone.utc)
        elapsed_sec = round(time.time() - start_time, 3)

        logger.info(
            "Transformation workflow '%s' finished with status '%s' in %.3fs "
            "(completed: %d, blocked: %d, failed: %d)",
            workflow.id,
            final_status.value,
            elapsed_sec,
            completed_count,
            blocked_count,
            failed_count,
        )

        return TransformationWorkflowResult(
            workflow_id=workflow.id,
            job_id=workflow.job_id,
            plan_id=plan.id,
            canonical_id=canonical.id,
            status=final_status,
            artifacts=artifacts,
            blocked_contracts=blocked_contracts,
            failed_tasks=failed_tasks,
            completed_deliverable_ids=completed_deliverable_ids,
            total_deliverables=total_count,
            execution_time_seconds=elapsed_sec,
        )

    def execute_job_workflow(
        self,
        job: TransformationJob,
        handoff_svc: Optional[Any] = None,
    ) -> TransformationWorkflowResult:
        """Authoritative execution entrance for a TransformationJob."""
        plan_dict = job.configuration.format_overrides.get("output_plan")
        if not plan_dict:
            raise BadRequestError(f"Job '{job.id}' does not contain an output_plan manifest")

        plan = OutputPlan.model_validate(plan_dict)
        canonical = self.job_svc.get_canonical_content(plan.canonical_id)

        workflow = self.build_workflow(plan=plan, job_id=job.id)
        if job.state == JobState.CANCELLED:
            self.cancel_workflow(workflow.id)

        return self.execute_workflow(
            workflow=workflow,
            plan=plan,
            canonical=canonical,
            config=job.configuration,
            project_id=job.project_id,
            handoff_svc=handoff_svc,
        )

    def execute_single_task(self, job_id: str, deliverable_id: str) -> Artifact:
        """Idempotently execute a single planned deliverable from a job contract."""
        job = self.job_svc.get_job(job_id)
        if job.state == JobState.CANCELLED:
            raise BadRequestError(f"Cannot execute deliverable '{deliverable_id}': Job '{job_id}' is cancelled")
        plan_dict = job.configuration.format_overrides.get("output_plan")
        if not plan_dict:
            raise BadRequestError(f"Job '{job_id}' does not contain an output_plan manifest")

        plan = OutputPlan.model_validate(plan_dict)
        deliverable = next((d for d in plan.deliverables if d.deliverable_id == deliverable_id), None)
        if not deliverable:
            raise EntityNotFoundError("PlannedDeliverable", deliverable_id)

        canonical = self.job_svc.get_canonical_content(plan.canonical_id)

        # Check existing artifact
        existing = self._find_existing_artifact(job_id=job_id, deliverable_id=deliverable_id)
        if existing:
            return existing

        art = self.engine_router.dispatch(
            route=deliverable.route,
            deliverable=deliverable,
            canonical=canonical,
            config=job.configuration,
            project_id=job.project_id,
            job_id=job.id,
        )
        if not art:
            raise BadRequestError(f"Engine dispatch produced no artifact for deliverable '{deliverable_id}'")
        return art

    def _find_existing_artifact(self, job_id: str, deliverable_id: str) -> Optional[Artifact]:
        """Inspect storage and SQLite repository to verify if an intact artifact already exists."""
        try:
            candidates = self.artifact_svc.list_artifacts(job_id=job_id)
            for c in candidates:
                if c.metadata and c.metadata.get("deliverable_id") == deliverable_id:
                    # Check physical file integrity
                    if c.storage_ref and self.storage_svc.file_exists(c.storage_ref):
                        file_bytes = self.storage_svc.read_file(c.storage_ref)
                        if self.storage_svc.compute_sha256(file_bytes) == c.content_hash:
                            return c
            return None
        except Exception:
            return None

    @staticmethod
    def _sanitize_error(exc: Exception, fmt: OutputFormat) -> str:
        """Produce clean user-facing error message without leaking stack traces or filesystem paths."""
        err_str = str(exc)
        if "UnsupportedFormatError" in type(exc).__name__:
            return f"Format '{fmt.value}' is not supported by the assigned engine"
        elif "UnimplementedEngineError" in type(exc).__name__:
            return f"Execution engine for '{fmt.value}' is not yet implemented"
        elif "character limit" in err_str.lower():
            return f"Generation constraint violation: Twitter character limit exceeded"
        else:
            return f"Generation synthesis failed for '{fmt.value}' deliverable"


workflow_orchestrator = TransformationWorkflowOrchestrator()
