"""Unit and integration tests for TransformationWorkflowOrchestrator (Phase D6.4).

Verifies:
- Independent CanonicalContent execution (no artificial DAG dependencies).
- Pure native workflow completes with status COMPLETED and real artifacts.
- Pure external workflow yields status WAITING_EXTERNAL with zero fake files.
- Mixed workflow yields status PARTIALLY_COMPLETED.
- Retry idempotency keyed by (job_id, deliverable_id) prevents duplicate artifacts.
- Task error strings are sanitized user-facing messages without raw tracebacks.
- Task-boundary cancellation: active task finishes, pending tasks skipped.
- Filesystem snapshot asserts zero fake office/video deliverables.
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from app.exceptions import BadRequestError
from app.models.content import CanonicalContent, CanonicalDataPoint, CanonicalFact, CanonicalIntent
from app.models.enums import JobState, OutputFormat, WorkflowStatus
from app.models.generation_config import GenerationConfig
from app.models.workflow import TaskStatus
from app.services.chat_service import chat_service
from app.services.job_service import job_service
from app.services.project_service import project_service
from app.services.source_service import source_service
from app.services.transform_service import transform_service
from app.services.transformation.workflow_orchestrator import (
    TransformationWorkflowOrchestrator,
    workflow_orchestrator,
)
from app.storage.service import storage_service


@pytest.fixture
def workflow_setup():
    """Setup real SQLite project, chat session, source, and CanonicalContent."""
    proj = project_service.create_project("D6.4 Orchestrator Test Project")
    src = source_service.register_text_source(
        name="Telemetry Executive Brief",
        text_content="Core metrics report for global operations and edge resilience.",
        project_id=proj.id,
    )
    chat = chat_service.create_session("D6.4 Chat Session", project_id=proj.id)

    canonical = CanonicalContent(
        source_ids=[src.id],
        title="Q3 Global Operations Brief",
        context="Quarterly analysis of infrastructure telemetry and reliability.",
        intent=CanonicalIntent(
            primary_purpose="Brief leadership on security and efficiency",
            target_audiences=["Executive Leadership"],
            core_narrative="Infrastructure achieved 99.9% uptime with zero critical regressions.",
        ),
        facts=[
            CanonicalFact(
                statement="Edge firewall mitigated 120,000 intrusion anomalies in Q3.",
                confidence=0.98,
                evidence_status="verified",
            ),
        ],
        data_points=[
            CanonicalDataPoint(metric="Mitigated Anomalies", value="120,000", unit="events", context="Q3"),
            CanonicalDataPoint(metric="System Availability", value="99.9%", unit="percent", context="Global"),
        ],
        recommendations=["Migrate primary ingestion pipeline to async event queue."],
        content_hash="d" * 64,
        created_at=datetime.now(timezone.utc),
    )
    canonical = job_service.save_canonical_content(canonical)

    return {
        "project": proj,
        "source": src,
        "chat": chat,
        "canonical": canonical,
    }


def test_independent_task_execution_no_artificial_dag(workflow_setup):
    """Verify tasks are planned as independent siblings derived from CanonicalContent."""
    canonical = workflow_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN, OutputFormat.LINKEDIN, OutputFormat.INFOGRAPHIC],
        canonical_id=canonical.id,
        project_id=workflow_setup["project"].id,
    )

    plan_dict = job.configuration.format_overrides.get("output_plan")
    from app.models.transformation import OutputPlan
    plan = OutputPlan.model_validate(plan_dict)

    workflow = workflow_orchestrator.build_workflow(plan=plan, job_id=job.id)
    assert len(workflow.tasks) == 3
    assert workflow.task_order == [d.deliverable_id for d in plan.deliverables]

    # All tasks are initialized to PENDING without artificial inter-task dependencies
    for task in workflow.tasks.values():
        assert task.status == TaskStatus.PENDING
        assert task.is_implemented is True


def test_pure_native_workflow_completes(workflow_setup):
    """Verify a workflow with all native formats completes with status COMPLETED and real artifacts."""
    canonical = workflow_setup["canonical"]
    formats = [
        OutputFormat.MARKDOWN,
        OutputFormat.HTML,
        OutputFormat.LINKEDIN,
        OutputFormat.TWITTER,
        OutputFormat.INFOGRAPHIC,
    ]
    job = transform_service.create_transform_contract(
        requested_formats=formats,
        canonical_id=canonical.id,
        project_id=workflow_setup["project"].id,
    )

    result = transform_service.orchestrate_transformation(job.id)

    assert result.status == WorkflowStatus.COMPLETED
    assert result.total_deliverables == 5
    assert len(result.artifacts) == 5
    assert len(result.completed_deliverable_ids) == 5
    assert len(result.blocked_contracts) == 0
    assert len(result.failed_tasks) == 0

    # Verify physical file existence and non-zero byte size for each real deliverable
    for art in result.artifacts:
        assert storage_service.file_exists(art.storage_ref)
        raw_bytes = storage_service.read_file(art.storage_ref)
        assert len(raw_bytes) > 0
        assert storage_service.compute_sha256(raw_bytes) == art.content_hash


def test_pure_external_workflow_waiting_external(workflow_setup):
    """Verify a workflow requesting only external deliverables produces status WAITING_EXTERNAL."""
    canonical = workflow_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.PRESENTATION, OutputFormat.VIDEO],
        canonical_id=canonical.id,
        project_id=workflow_setup["project"].id,
    )

    result = transform_service.orchestrate_transformation(job.id)

    assert result.status == WorkflowStatus.WAITING_EXTERNAL
    assert result.total_deliverables == 2
    assert len(result.artifacts) == 0
    assert len(result.completed_deliverable_ids) == 0
    assert len(result.blocked_contracts) == 2
    assert len(result.failed_tasks) == 0

    # Verify contracts are prepared with canonical provenance
    for deliv_id, payload in result.blocked_contracts.items():
        assert "canonical_id" in payload or "options" in payload


def test_mixed_workflow_partially_completes(workflow_setup):
    """Verify a mixed native + external workflow produces status PARTIALLY_COMPLETED."""
    canonical = workflow_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN, OutputFormat.PRESENTATION],
        canonical_id=canonical.id,
        project_id=workflow_setup["project"].id,
    )

    result = transform_service.orchestrate_transformation(job.id)

    assert result.status == WorkflowStatus.PARTIALLY_COMPLETED
    assert result.total_deliverables == 2
    assert len(result.artifacts) == 1
    assert len(result.completed_deliverable_ids) == 1
    assert len(result.blocked_contracts) == 1
    assert result.artifacts[0].file_format == ".md"


def test_retry_idempotency_prevents_duplicate_artifacts(workflow_setup):
    """Verify that re-executing or retrying a deliverable reuses the existing intact artifact."""
    canonical = workflow_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN],
        canonical_id=canonical.id,
        project_id=workflow_setup["project"].id,
    )

    # First execution
    result1 = transform_service.orchestrate_transformation(job.id)
    assert len(result1.artifacts) == 1
    first_artifact_id = result1.artifacts[0].id

    # Second execution (idempotent run)
    result2 = transform_service.orchestrate_transformation(job.id)
    assert len(result2.artifacts) == 1
    second_artifact_id = result2.artifacts[0].id

    # Must reuse the same artifact identity rather than duplicating
    assert first_artifact_id == second_artifact_id


def test_task_error_is_safe_user_message(workflow_setup, monkeypatch):
    """Verify task.error contains sanitized user text and never leaks stack traces or system paths."""
    canonical = workflow_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN],
        canonical_id=canonical.id,
        project_id=workflow_setup["project"].id,
    )

    # Force simulated error inside adapter dispatch
    def mock_failing_dispatch(*args, **kwargs):
        raise RuntimeError("Internal database connection error at /var/secret/path.py:L123")

    monkeypatch.setattr(workflow_orchestrator.engine_router, "dispatch", mock_failing_dispatch)

    result = transform_service.orchestrate_transformation(job.id)

    assert result.status == WorkflowStatus.FAILED
    assert len(result.failed_tasks) == 1
    error_msg = result.failed_tasks[0]["error"]

    # Safe error assertions
    assert "Traceback" not in error_msg
    assert "/var/secret" not in error_msg
    assert "Generation synthesis failed" in error_msg


def test_task_boundary_cancellation(workflow_setup):
    """Verify that cancelling a workflow skips subsequent pending tasks without corrupting state."""
    canonical = workflow_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN, OutputFormat.HTML, OutputFormat.LINKEDIN],
        canonical_id=canonical.id,
        project_id=workflow_setup["project"].id,
    )

    plan_dict = job.configuration.format_overrides.get("output_plan")
    from app.models.transformation import OutputPlan
    plan = OutputPlan.model_validate(plan_dict)

    wf = workflow_orchestrator.build_workflow(plan=plan, job_id=job.id)

    # Trigger cancellation before execution begins
    workflow_orchestrator.cancel_workflow(wf.id)

    result = workflow_orchestrator.execute_workflow(
        workflow=wf,
        plan=plan,
        canonical=canonical,
        config=job.configuration,
        project_id=job.project_id,
    )

    assert result.status == WorkflowStatus.CANCELLED
    assert len(result.artifacts) == 0
    # All tasks should be marked SKIPPED
    for task in wf.tasks.values():
        assert task.status == TaskStatus.SKIPPED


def test_task_boundary_cancellation_prevents_newly_starting_tasks(workflow_setup, monkeypatch):
    """Verify that cancellation during an active task allows that task to finish,
    but explicitly prevents newly starting tasks from beginning, marking pending tasks SKIPPED.
    """
    canonical = workflow_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN, OutputFormat.HTML, OutputFormat.LINKEDIN],
        canonical_id=canonical.id,
        project_id=workflow_setup["project"].id,
    )

    plan_dict = job.configuration.format_overrides.get("output_plan")
    from app.models.transformation import OutputPlan
    plan = OutputPlan.model_validate(plan_dict)

    wf = workflow_orchestrator.build_workflow(plan=plan, job_id=job.id)

    original_dispatch = workflow_orchestrator.engine_router.dispatch
    dispatch_calls = []

    def cancelling_dispatch(*args, **kwargs):
        art = original_dispatch(*args, **kwargs)
        deliv = kwargs.get("deliverable") or (args[1] if len(args) > 1 else None)
        dispatch_calls.append(deliv.format if deliv else None)
        # Cancel the workflow while the first active task is finishing
        workflow_orchestrator.cancel_workflow(wf.id)
        return art

    monkeypatch.setattr(workflow_orchestrator.engine_router, "dispatch", cancelling_dispatch)

    result = workflow_orchestrator.execute_workflow(
        workflow=wf,
        plan=plan,
        canonical=canonical,
        config=job.configuration,
        project_id=job.project_id,
    )

    # 1. Overall workflow status must be CANCELLED
    assert result.status == WorkflowStatus.CANCELLED

    # 2. Dispatch must have executed ONLY for the first active task (MARKDOWN)
    assert len(dispatch_calls) == 1
    assert dispatch_calls[0] == OutputFormat.MARKDOWN

    # 3. Active task finished cleanly with registered artifact preserved
    deliv_ids = wf.task_order
    task_markdown = wf.tasks[deliv_ids[0]]
    assert task_markdown.status == TaskStatus.COMPLETED
    assert task_markdown.error is None
    assert len(result.artifacts) == 1
    assert result.artifacts[0].file_format == ".md"
    assert result.completed_deliverable_ids == [deliv_ids[0]]

    # 4. Newly starting tasks were explicitly prevented from starting and marked SKIPPED
    task_html = wf.tasks[deliv_ids[1]]
    task_linkedin = wf.tasks[deliv_ids[2]]
    assert task_html.status == TaskStatus.SKIPPED
    assert "Execution cancelled prior to task start" in task_html.error
    assert task_linkedin.status == TaskStatus.SKIPPED
    assert "Execution cancelled prior to task start" in task_linkedin.error


def test_cancelled_job_state_prevents_task_execution(workflow_setup):
    """Verify that attempting to execute tasks on an already-cancelled job aborts immediately."""
    canonical = workflow_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN, OutputFormat.HTML],
        canonical_id=canonical.id,
        project_id=workflow_setup["project"].id,
    )
    # Transition job to CANCELLED state
    job_service.update_progress(
        job_id=job.id,
        state=JobState.CANCELLED,
        progress=0.0,
        current_stage="Job cancelled by user",
    )
    cancelled_job = job_service.get_job(job.id)

    # 1. execute_job_workflow skips all deliverables
    result = workflow_orchestrator.execute_job_workflow(cancelled_job)
    assert result.status == WorkflowStatus.CANCELLED
    assert len(result.artifacts) == 0
    assert len(result.completed_deliverable_ids) == 0

    # 2. execute_single_task refuses to run
    plan_dict = cancelled_job.configuration.format_overrides.get("output_plan")
    from app.models.transformation import OutputPlan
    plan = OutputPlan.model_validate(plan_dict)
    first_deliv_id = plan.deliverables[0].deliverable_id

    with pytest.raises(BadRequestError, match="is cancelled"):
        workflow_orchestrator.execute_single_task(job.id, first_deliv_id)


def test_snapshot_zero_fake_office_and_video_artifacts_during_orchestration(workflow_setup):
    """Snapshot test confirming zero fake .docx, .pptx, .xlsx, or .mp4 deliverables leak to disk."""
    base_data_dir = Path(storage_service.base_dir)

    def count_forbidden_files() -> int:
        forbidden_exts = {".docx", ".pptx", ".xlsx", ".mp4"}
        return sum(
            1 for p in base_data_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in forbidden_exts
        )

    initial_forbidden = count_forbidden_files()

    canonical = workflow_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[
            OutputFormat.DOCUMENT,
            OutputFormat.PRESENTATION,
            OutputFormat.SPREADSHEET,
            OutputFormat.VIDEO,
            OutputFormat.MARKDOWN,
        ],
        canonical_id=canonical.id,
        project_id=workflow_setup["project"].id,
    )

    result = transform_service.orchestrate_transformation(job.id)

    # 1 native completed, 4 external guarded
    assert result.status == WorkflowStatus.PARTIALLY_COMPLETED
    assert len(result.artifacts) == 1
    assert len(result.blocked_contracts) == 4

    post_forbidden = count_forbidden_files()
    assert post_forbidden == initial_forbidden, (
        f"Forbidden fake files leaked to disk: expected {initial_forbidden}, found {post_forbidden}"
    )
