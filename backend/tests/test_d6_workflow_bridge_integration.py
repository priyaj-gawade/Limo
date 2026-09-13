"""Integration tests for LangGraphBridge and D6.4 Workflow Orchestrator."""

from datetime import datetime, timezone
import pytest

from app.agent.orchestration.bridge import LangGraphBridge
from app.agent.orchestration.models import WorkflowConfig, WorkflowStage, WorkflowStatus
from app.models.content import CanonicalContent, CanonicalDataPoint, CanonicalFact, CanonicalIntent
from app.models.enums import OutputFormat
from app.services.chat_service import chat_service
from app.services.job_service import job_service
from app.services.project_service import project_service
from app.services.source_service import source_service
from app.services.transform_service import transform_service


@pytest.fixture
def bridge_setup():
    """Setup real SQLite project, chat session, source, and CanonicalContent."""
    proj = project_service.create_project("D6.4 Bridge Test Project")
    src = source_service.register_text_source(
        name="Security Architecture Analysis",
        text_content="Threat vector report across enterprise perimeter nodes.",
        project_id=proj.id,
    )
    chat = chat_service.create_session("D6.4 Bridge Session", project_id=proj.id)

    canonical = CanonicalContent(
        source_ids=[src.id],
        title="Enterprise Perimeter Security Analysis",
        context="Quarterly analysis of threat vectors and defense postures.",
        intent=CanonicalIntent(
            primary_purpose="Brief leadership on security posture",
            target_audiences=["Chief Information Security Officer"],
            core_narrative="All critical boundary firewalls inspected with zero breaches.",
        ),
        facts=[
            CanonicalFact(
                statement="Zero anomalous packets bypassed perimeter gateway filters.",
                confidence=0.99,
                evidence_status="verified",
            ),
        ],
        data_points=[
            CanonicalDataPoint(metric="Bypassed Anomalies", value="0", unit="packets", context="Perimeter"),
        ],
        recommendations=["Sustain multi-factor cryptographic key rotation."],
        content_hash="e" * 64,
        created_at=datetime.now(timezone.utc),
    )
    canonical = job_service.save_canonical_content(canonical)

    return {
        "project": proj,
        "source": src,
        "chat": chat,
        "canonical": canonical,
    }


@pytest.mark.asyncio
async def test_langgraph_bridge_dispatches_generate_stage(bridge_setup):
    """Verify LangGraphBridge dispatches WorkflowStage.GENERATE via the orchestrator."""
    canonical = bridge_setup["canonical"]
    proj = bridge_setup["project"]

    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN, OutputFormat.LINKEDIN],
        canonical_id=canonical.id,
        project_id=proj.id,
    )

    bridge = LangGraphBridge()
    bridge.register_default_generation_handler(service=transform_service)

    config = WorkflowConfig(
        job_id=job.id,
        project_id=proj.id,
        target_stages=[WorkflowStage.GENERATE],
    )
    bridge.accept_configuration(config)

    state = await bridge.dispatch_next_stage(job.id)

    assert state.status == WorkflowStatus.STAGE_COMPLETED
    assert WorkflowStage.GENERATE in state.completed_stages

    # Verify stage_data has the structured TransformationWorkflowResult dictionary
    generate_data = state.stage_data.get("generate")
    assert generate_data is not None
    assert generate_data["status"] == "completed"
    assert generate_data["total_deliverables"] == 2
    assert len(generate_data["artifacts"]) == 2
    assert len(generate_data["completed_deliverable_ids"]) == 2
