"""Integration tests for Native Deliverable Execution & External Boundary Protection (Phase D6.3).

Verifies:
- End-to-end execution of native deliverables via TransformService.execute_native_deliverables
- Job progress tracking and state transitions (COMPLETED when all native, PROCESSING when external pending)
- External engine dispatch remains blocked with UnimplementedEngineError
- Snapshot test confirms zero fake .docx, .pptx, .xlsx, or .mp4 files are generated
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest

from app.exceptions import UnimplementedEngineError
from app.models.content import CanonicalContent, CanonicalDataPoint, CanonicalFact, CanonicalIntent
from app.models.enums import JobState, OutputFormat
from app.models.generation_config import GenerationConfig
from app.services.chat_service import chat_service
from app.services.job_service import job_service
from app.services.project_service import project_service
from app.services.source_service import source_service
from app.services.transform_service import transform_service
from app.storage.service import storage_service


@pytest.fixture
def execution_setup():
    """Setup real SQLite project, chat, text source, and CanonicalContent."""
    proj = project_service.create_project("D6.3 Execution Test Project")
    src = source_service.register_text_source(
        name="Quarterly Defense Review",
        text_content="Telemetry systems across peripheral edges inspected for cryptographic posture.",
        project_id=proj.id,
    )
    chat = chat_service.create_session("D6.3 Chat Session", project_id=proj.id)

    canonical = CanonicalContent(
        source_ids=[src.id],
        title="Quarterly Perimeter Defense Review",
        context="Quarterly analysis of cloud telemetry posture.",
        intent=CanonicalIntent(
            primary_purpose="Report posture metrics to security council",
            target_audiences=["Security Council"],
            core_narrative="Quarterly audit confirms perimeter resilience with 99.8% uptime.",
        ),
        facts=[
            CanonicalFact(
                statement="Edge firewall filters blocked 45,000 unauthorized connection attempts.",
                confidence=0.97,
                evidence_status="verified",
            ),
        ],
        data_points=[
            CanonicalDataPoint(metric="Blocked Probes", value="45,000", unit="events", context="Q3"),
            CanonicalDataPoint(metric="System Uptime", value="99.8%", unit="percent", context="Perimeter"),
        ],
        recommendations=["Upgrade remaining secondary gateways by Q4."],
        content_hash="c" * 64,
        created_at=datetime.now(timezone.utc),
    )
    saved_canonical = job_service.save_canonical_content(canonical)

    return {"project": proj, "source": src, "chat": chat, "canonical": saved_canonical}


def test_pure_native_job_executes_to_completion(execution_setup):
    """D6.3: A transformation job requesting only native formats executes and reaches COMPLETED state."""
    canonical = execution_setup["canonical"]
    proj = execution_setup["project"]
    chat = execution_setup["chat"]

    # 1. Create contract with native formats
    native_formats = [
        OutputFormat.MARKDOWN,
        OutputFormat.HTML,
        OutputFormat.LINKEDIN,
        OutputFormat.TWITTER,
        OutputFormat.INFOGRAPHIC,
    ]
    job = transform_service.create_transform_contract(
        requested_formats=native_formats,
        canonical_id=canonical.id,
        project_id=proj.id,
        session_id=chat.id,
        prompt="Prepare full digital release package",
    )

    assert job.state == JobState.QUEUED
    assert len(job.artifact_ids) == 0

    # 2. Execute all native deliverables in the plan
    artifacts = transform_service.orchestrate_transformation(job.id).artifacts

    assert len(artifacts) == 5
    formats = {a.file_format for a in artifacts}
    assert ".md" in formats
    assert ".html" in formats
    assert ".json" in formats
    assert ".svg" in formats

    # 3. Verify job reached COMPLETED with 100% progress
    updated_job = job_service.get_job(job.id)
    assert updated_job.state == JobState.COMPLETED
    assert updated_job.progress == 1.0
    assert len(updated_job.artifact_ids) == 5


def test_mixed_job_executes_native_and_leaves_external_pending(execution_setup):
    """D6.3: A job with native and external formats executes native items, keeping external items pending."""
    canonical = execution_setup["canonical"]
    proj = execution_setup["project"]

    # 1. Request 1 native format (MARKDOWN) and 1 external format (PRESENTATION)
    mixed_formats = [OutputFormat.MARKDOWN, OutputFormat.PRESENTATION]
    job = transform_service.create_transform_contract(
        requested_formats=mixed_formats,
        canonical_id=canonical.id,
        project_id=proj.id,
    )

    # 2. Execute native deliverables
    artifacts = transform_service.orchestrate_transformation(job.id).artifacts
    assert len(artifacts) == 1
    assert artifacts[0].file_format == ".md"

    # 3. Verify job state is PARTIALLY_COMPLETED or PROCESSING (50% progress, not COMPLETED)
    updated_job = job_service.get_job(job.id)
    assert updated_job.state in (JobState.PROCESSING, JobState.PARTIALLY_COMPLETED)
    assert updated_job.progress == 0.5
    assert len(updated_job.artifact_ids) == 1

    # 4. Attempting to execute the presentation deliverable directly fails explicitly
    plan_dict = updated_job.configuration.format_overrides["output_plan"]
    pres_deliverable_id = next(d["deliverable_id"] for d in plan_dict["deliverables"] if d["format"] == "presentation")

    with pytest.raises(UnimplementedEngineError) as exc_info:
        transform_service.execute_deliverable(deliverable_id=pres_deliverable_id, job_id=job.id)

    assert exc_info.value.status_code == 501
    assert "genoffice_slides" in exc_info.value.message


def test_snapshot_zero_fake_office_and_video_artifacts(execution_setup):
    """D6.3 Integrity: Executing native and external planning never produces fake .docx, .pptx, or .mp4 files."""
    canonical = execution_setup["canonical"]

    target_dirs = [
        storage_service.artifacts_dir,
        storage_service.temp_dir,
        storage_service.sources_dir,
        Path("."),
    ]
    prohibited_exts = {".docx", ".pptx", ".xlsx", ".mp4"}

    def get_prohibited_snapshot():
        found = set()
        for d in target_dirs:
            if d.exists():
                for p in d.rglob("*"):
                    if p.is_file() and p.suffix.lower() in prohibited_exts:
                        found.add(p.resolve())
        return found

    before = get_prohibited_snapshot()

    # Create and execute transform contract across all formats
    all_formats = [
        OutputFormat.MARKDOWN,
        OutputFormat.PRESENTATION,
        OutputFormat.SPREADSHEET,
        OutputFormat.DOCUMENT,
        OutputFormat.VIDEO,
    ]
    job = transform_service.create_transform_contract(
        requested_formats=all_formats,
        canonical_id=canonical.id,
    )
    transform_service.orchestrate_transformation(job.id)

    after = get_prohibited_snapshot()
    new_prohibited = after - before

    assert len(new_prohibited) == 0, f"Leaked prohibited fake office/video deliverables: {new_prohibited}"
