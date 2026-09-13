"""Unit tests for Phase D4.6: LangGraphBridge workflow contract and explicit stage failure."""

import pytest
from app.agent.orchestration.bridge import LangGraphBridge, UnimplementedStageError
from app.agent.orchestration.models import WorkflowConfig, WorkflowStage, WorkflowStatus


def test_workflow_configuration_accepted():
    bridge = LangGraphBridge()
    config = WorkflowConfig(
        job_id="job_orch_1",
        project_id="proj_1",
        source_ids=["src_1", "src_2"],
        requested_formats=["summary"],
    )

    state = bridge.accept_configuration(config)
    assert state.job_id == "job_orch_1"
    assert state.status == WorkflowStatus.PENDING
    assert bridge.get_state("job_orch_1") is not None


@pytest.mark.asyncio
async def test_unimplemented_stage_fails_explicitly():
    """MUST-FIX #3: Bridge must fail explicitly without creating fake implementations for missing stages."""
    bridge = LangGraphBridge()
    config = WorkflowConfig(
        job_id="job_orch_2",
        project_id="proj_1",
        target_stages=[WorkflowStage.INGEST],
    )
    bridge.accept_configuration(config)

    # Ingest stage has no registered handler in Phase D4.6
    with pytest.raises(UnimplementedStageError) as exc_info:
        await bridge.dispatch_next_stage("job_orch_2")

    assert "not implemented in Phase D4.6" in str(exc_info.value)
    state = bridge.get_state("job_orch_2")
    assert state.status == WorkflowStatus.FAILED


@pytest.mark.asyncio
async def test_registered_stage_handler_executes():
    bridge = LangGraphBridge()
    config = WorkflowConfig(
        job_id="job_orch_3",
        project_id="proj_1",
        target_stages=[WorkflowStage.INGEST],
    )
    bridge.accept_configuration(config)

    # Register real handler for stage
    async def ingest_handler(st):
        return {"canonical_id": "canon_123", "status": "extracted"}

    bridge.register_stage_handler(WorkflowStage.INGEST, ingest_handler)
    state = await bridge.dispatch_next_stage("job_orch_3")

    assert state.status == WorkflowStatus.STAGE_COMPLETED
    assert WorkflowStage.INGEST in state.completed_stages
    assert state.stage_data["ingest"]["canonical_id"] == "canon_123"
