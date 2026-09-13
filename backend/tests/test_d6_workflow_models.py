"""Unit tests for Phase D6.4: Workflow Domain Models, Tasks, and Frozen Results."""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from app.models.artifact import Artifact
from app.models.enums import ArtifactType, OutputFormat, WorkflowStatus
from app.models.transformation import EngineType
from app.models.workflow import (
    DeliverableTask,
    TaskStatus,
    TransformationWorkflow,
    TransformationWorkflowResult,
)


def test_deliverable_task_lifecycle_and_validation():
    task = DeliverableTask(
        deliverable_id="del_md_01",
        format=OutputFormat.MARKDOWN,
        engine_type=EngineType.NATIVE_MARKDOWN,
        is_implemented=True,
    )
    assert task.task_id.startswith("task_")
    assert task.status == TaskStatus.PENDING
    assert task.retry_count == 0
    assert task.artifact_id is None
    assert task.contract_payload is None
    assert task.error is None

    # Update to running
    now = datetime.now(timezone.utc)
    task.status = TaskStatus.RUNNING
    task.started_at = now
    assert task.status == TaskStatus.RUNNING

    # Complete
    task.status = TaskStatus.COMPLETED
    task.artifact_id = "art_12345"
    task.completed_at = datetime.now(timezone.utc)
    assert task.status == TaskStatus.COMPLETED


def test_deliverable_task_id_validation():
    with pytest.raises(ValidationError):
        DeliverableTask(
            task_id="invalid_id",
            deliverable_id="del_01",
            format=OutputFormat.MARKDOWN,
            engine_type=EngineType.NATIVE_MARKDOWN,
            is_implemented=True,
        )


def test_transformation_workflow_construction():
    task1 = DeliverableTask(
        deliverable_id="del_1",
        format=OutputFormat.MARKDOWN,
        engine_type=EngineType.NATIVE_MARKDOWN,
        is_implemented=True,
    )
    task2 = DeliverableTask(
        deliverable_id="del_2",
        format=OutputFormat.PRESENTATION,
        engine_type=EngineType.GENOFFICE_SLIDES,
        is_implemented=False,
    )

    wf = TransformationWorkflow(
        job_id="job_wf_1",
        plan_id="plan_wf_1",
        canonical_id="can_wf_1",
        tasks={"del_1": task1, "del_2": task2},
        task_order=["del_1", "del_2"],
    )

    assert wf.id.startswith("wf_")
    assert wf.status == WorkflowStatus.PENDING
    assert len(wf.tasks) == 2
    assert wf.task_order == ["del_1", "del_2"]


def test_transformation_workflow_result_frozen_immutability():
    """Verify that TransformationWorkflowResult is frozen and cannot be mutated."""
    dummy_artifact = Artifact(
        id="art_test",
        title="Test Doc",
        artifact_type=ArtifactType.DOC,
        file_format=".md",
        storage_ref="artifacts/art_test/test.md",
        size_bytes=100,
        content_hash="a" * 64,
    )

    result = TransformationWorkflowResult(
        workflow_id="wf_frozen_test",
        job_id="job_frozen_test",
        plan_id="plan_frozen_test",
        canonical_id="can_frozen_test",
        status=WorkflowStatus.COMPLETED,
        artifacts=[dummy_artifact],
        completed_deliverable_ids=["del_md"],
        total_deliverables=1,
        execution_time_seconds=0.125,
    )

    assert result.status == WorkflowStatus.COMPLETED
    assert len(result.artifacts) == 1

    # Attempting mutation must raise ValidationError due to ConfigDict(frozen=True)
    with pytest.raises(ValidationError):
        result.status = WorkflowStatus.FAILED


def test_workflow_status_includes_waiting_external():
    """Verify WAITING_EXTERNAL is a valid WorkflowStatus enum member."""
    assert WorkflowStatus.WAITING_EXTERNAL == "waiting_external"
    assert WorkflowStatus.PARTIALLY_COMPLETED == "partially_completed"
    assert WorkflowStatus.CANCELLED == "cancelled"
