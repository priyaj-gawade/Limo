"""End-to-end integration tests for Phase D6: Transformation & Output Planning.

Verifies:
- End-to-end flow from real CanonicalContent -> TransformationRequest -> OutputPlan -> SQLite Job Contract
- Direct planning via TransformService.plan_transformation
- TransformContractTool execution with canonical_id and configuration
- Zero mock or fake deliverables generated on disk
- LangGraphBridge integration with explicit failure on unimplemented engines
"""

from datetime import datetime, timezone
import os
import pytest

from app.agent.orchestration.bridge import LangGraphBridge
from app.agent.orchestration.models import WorkflowConfig, WorkflowStage, WorkflowStatus
from app.agent.tools.transform_tool import TransformContractTool
from app.exceptions import UnimplementedEngineError
from app.models.content import CanonicalContent, CanonicalFact, CanonicalIntent
from app.models.enums import CommunicationObjective, JobState, OutputFormat
from app.models.generation_config import GenerationConfig, PresentationOptions
from app.services.chat_service import chat_service
from app.services.job_service import job_service
from app.services.project_service import project_service
from app.services.source_service import source_service
from app.services.transform_service import transform_service
from app.services.transformation.engine_router import engine_router
from app.services.transformation.output_planner import output_planner


@pytest.fixture
def test_setup():
    """Setup real SQLite project, source, chat session, and CanonicalContent."""
    proj = project_service.create_project("D6 Orchestration Project")
    src = source_service.register_text_source(
        name="Security Advisory 2026",
        text_content="Critical zero-day exploit detected in telemetry edge gateways.",
        project_id=proj.id,
    )
    chat = chat_service.create_session("D6 Chat Session", project_id=proj.id)

    canonical = CanonicalContent(
        source_ids=[src.id],
        title="Telemetry Zero-Day Advisory",
        context="Investigation into edge telemetry appliance intrusions.",
        intent=CanonicalIntent(
            primary_purpose="Alert executive leadership to immediate patch requirements",
            target_audiences=["Executive Board", "CISO Office"],
            core_narrative="Zero-day vulnerability requires immediate emergency patching.",
        ),
        facts=[
            CanonicalFact(statement="Telemetry gateways running firmware < 4.2 are exploitable.", confidence=0.95),
        ],
        claims=[],
        events=[],
        data_points=[],
        recommendations=["Deploy emergency patch within 24 hours"],
        references=[],
        content_hash="d" * 64,
        created_at=datetime.now(timezone.utc),
    )
    saved_canonical = job_service.save_canonical_content(canonical)

    return {
        "project": proj,
        "source": src,
        "chat": chat,
        "canonical": saved_canonical,
    }


def test_end_to_end_contract_pipeline_with_real_canonical(test_setup):
    """D6 End-to-End: Real CanonicalContent -> D6.1 Config Reconciliation -> D6.2 OutputPlan -> SQLite Contract."""
    canonical = test_setup["canonical"]
    proj = test_setup["project"]
    chat = test_setup["chat"]

    cfg = GenerationConfig(
        presentation=PresentationOptions(slide_count=12, theme="slate_corporate"),
    )

    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.PRESENTATION, OutputFormat.SPREADSHEET, OutputFormat.DOCUMENT],
        canonical_id=canonical.id,
        configuration=cfg,
        project_id=proj.id,
        session_id=chat.id,
        prompt="Prepare full executive briefing deck, metrics workbook, and technical report",
    )

    assert job.id.startswith("job_")
    assert job.state == JobState.QUEUED
    assert job.progress == 0.0

    # Formats preserved
    assert OutputFormat.PRESENTATION in job.requested_formats
    assert OutputFormat.SPREADSHEET in job.requested_formats
    assert OutputFormat.DOCUMENT in job.requested_formats

    # Verify D6 OutputPlan and TransformationRequest persisted in configuration.format_overrides
    overrides = job.configuration.format_overrides
    assert "output_plan" in overrides
    assert "transformation_request" in overrides

    plan_data = overrides["output_plan"]
    assert plan_data["canonical_id"] == canonical.id
    assert plan_data["canonical_hash"] == canonical.content_hash
    assert plan_data["all_engines_available"] is False
    assert len(plan_data["deliverables"]) == 3

    # Check deliverable titles and routes
    deliv_formats = [d["format"] for d in plan_data["deliverables"]]
    assert "presentation" in deliv_formats
    assert "spreadsheet" in deliv_formats
    assert "document" in deliv_formats

    # Verify audience and objective were deterministically reconciled from canonical
    assert job.configuration.audience == "Executive Board"
    assert job.configuration.objective == CommunicationObjective.ALERT


def test_plan_transformation_direct_method(test_setup):
    """D6: Verify TransformService.plan_transformation returns strongly typed (request, plan)."""
    canonical = test_setup["canonical"]

    request, plan = transform_service.plan_transformation(
        canonical_id=canonical.id,
        requested_formats=[OutputFormat.PRESENTATION, OutputFormat.SPREADSHEET],
    )

    assert request.canonical_id == canonical.id
    assert request.canonical_hash == canonical.content_hash
    assert request.requested_formats == [OutputFormat.PRESENTATION, OutputFormat.SPREADSHEET]

    assert plan.request_id == request.id
    assert len(plan.deliverables) == 2
    assert plan.all_engines_available is False


@pytest.mark.asyncio
async def test_transform_contract_tool_integration_with_canonical_and_config(test_setup):
    """D6: TransformContractTool accepts canonical_id and configuration, queuing contract in SQLite."""
    canonical = test_setup["canonical"]
    proj = test_setup["project"]
    chat = test_setup["chat"]

    tool = TransformContractTool()

    result = await tool.execute({
        "requested_formats": ["presentation", "spreadsheet"],
        "canonical_id": canonical.id,
        "project_id": proj.id,
        "session_id": chat.id,
        "audience": "Board of Directors",
        "objective": "alert",
    })

    assert result.success is True
    job_id = result.output["job_id"]
    assert result.output["queued"] is True
    assert "presentation" in result.output["requested_formats"]
    assert "spreadsheet" in result.output["requested_formats"]

    # Retrieve from DB and verify
    stored_job = job_service.get_job(job_id)
    assert stored_job.configuration.audience == "Board of Directors"
    assert stored_job.configuration.objective == CommunicationObjective.ALERT
    assert "output_plan" in stored_job.configuration.format_overrides


def test_zero_fake_artifacts_generated(test_setup):
    """D6 Contract: Snapshot known artifact & working directories before/after to prove zero new artifacts."""
    from pathlib import Path
    from app.storage.service import storage_service

    canonical = test_setup["canonical"]

    # 1. Snapshot directories before test
    target_dirs = [
        storage_service.artifacts_dir,
        storage_service.temp_dir,
        storage_service.sources_dir,
        Path("."),
    ]
    deliverable_exts = {".pptx", ".docx", ".xlsx", ".mp4", ".pdf", ".svg"}

    def get_deliverable_snapshot():
        found = set()
        for d in target_dirs:
            if d.exists():
                for p in d.rglob("*"):
                    if p.is_file() and p.suffix.lower() in deliverable_exts:
                        found.add(p.resolve())
        return found

    before_snapshot = get_deliverable_snapshot()

    # 2. Run D6 Transformation Planning & Contract Creation
    transform_service.create_transform_contract(
        requested_formats=[
            OutputFormat.PRESENTATION,
            OutputFormat.SPREADSHEET,
            OutputFormat.DOCUMENT,
            OutputFormat.VIDEO,
            OutputFormat.PDF,
        ],
        canonical_id=canonical.id,
    )

    # Also test direct transformation planning
    transform_service.plan_transformation(
        canonical_id=canonical.id,
        requested_formats=[OutputFormat.PRESENTATION, OutputFormat.SPREADSHEET],
    )

    # 3. Snapshot directories after test and compare
    after_snapshot = get_deliverable_snapshot()
    new_files = after_snapshot - before_snapshot

    assert len(new_files) == 0, f"D6 planning leaked fake artifact files to disk: {new_files}"


@pytest.mark.asyncio
async def test_langgraph_bridge_fails_explicitly_on_unimplemented_generation_engine(test_setup):
    """D6 Contract: Bridge dispatches generation stage and fails explicitly with UnimplementedEngineError."""
    canonical = test_setup["canonical"]

    # Register output_planner handler on GENERATE stage
    bridge = LangGraphBridge()

    async def generate_stage_handler(config_dict):
        req, plan = transform_service.plan_transformation(
            canonical_id=canonical.id,
            requested_formats=[OutputFormat.PRESENTATION],
        )
        return engine_router.dispatch(
            route=plan.deliverables[0].route,
            deliverable=plan.deliverables[0],
            canonical=canonical,
            config=req.config,
        )

    bridge.register_stage_handler(WorkflowStage.GENERATE, generate_stage_handler)

    proj = test_setup["project"]
    wf_config = WorkflowConfig(
        job_id="job_bridge_test",
        project_id=proj.id,
        target_stages=[WorkflowStage.GENERATE],
    )
    bridge.accept_configuration(wf_config)

    # Executing the stage must fail explicitly with UnimplementedEngineError (HTTP 501)
    with pytest.raises(UnimplementedEngineError) as exc_info:
        await bridge.dispatch_next_stage("job_bridge_test")

    err = exc_info.value
    assert err.error_code == "UNIMPLEMENTED_ENGINE"
    assert err.status_code == 501
    assert "genoffice_slides" in err.message
