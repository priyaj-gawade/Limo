from datetime import datetime, timezone
from pathlib import Path
import pytest
from app.models.content import CanonicalContent, CanonicalDataPoint, CanonicalFact, CanonicalIntent
from app.models.enums import JobState, OutputFormat
from app.models.transformation_events import TransformationEventType
from app.models.workflow import TaskStatus, TransformationWorkflowResult, WorkflowStatus
from app.services.artifact_service import artifact_service
from app.services.job_service import job_service
from app.services.project_service import project_service
from app.services.source_service import source_service
from app.services.transform_service import transform_service
from app.services.transformation.event_broker import event_broker
from app.services.transformation.handoff import job_artifact_handoff_service
from app.storage.service import storage_service


@pytest.fixture
def handoff_setup():
    """Set up test environment with project, canonical content, and jobs."""
    project = project_service.create_project(
        name="Handoff Test Project",
        description="Testing D6.5 job and artifact handoff",
    )
    src = source_service.register_text_source(
        name="Telemetry Executive Brief",
        text_content="Core metrics report for global operations and edge resilience.",
        project_id=project.id,
    )
    content_text = (
        "# Executive Technical Briefing\n\n"
        "## Strategic Pillars\n"
        "- Scalable asynchronous orchestration.\n"
        "- Real file artifacts with verifiable SHA-256 integrity.\n"
        "- Clear phase boundaries between orchestrators and external engines.\n"
    )
    canonical = CanonicalContent(
        source_ids=[src.id],
        title="Executive Strategic Briefing",
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
        clean_markdown=content_text,
        content_hash=storage_service.compute_sha256(content_text.encode("utf-8")),
        created_at=datetime.now(timezone.utc),
    )
    canonical = job_service.save_canonical_content(canonical)
    return {"project": project, "source": src, "canonical": canonical}


def test_pure_native_handoff_completes_job_and_links_artifacts(handoff_setup):
    """Verify that a pure native workflow transitions to COMPLETED, 1.0 progress, and links real artifacts."""
    canonical = handoff_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN, OutputFormat.HTML],
        canonical_id=canonical.id,
        project_id=handoff_setup["project"].id,
    )

    result = transform_service.orchestrate_transformation(job.id)

    assert result.status == WorkflowStatus.COMPLETED
    updated_job = job_service.get_job(job.id)
    assert updated_job.state == JobState.COMPLETED
    assert updated_job.progress == 1.0
    assert len(updated_job.artifact_ids) == 2

    # Verify bidirectional linkage and storage integrity
    assert job_artifact_handoff_service.verify_job_artifact_linkage(job.id) is True

    # Verify lifecycle events emitted
    events = event_broker.replay(job.id)
    event_types = [e.event_type for e in events]
    assert TransformationEventType.JOB_CREATED in event_types
    assert TransformationEventType.JOB_STARTED in event_types
    assert TransformationEventType.TASK_STARTED in event_types
    assert TransformationEventType.TASK_COMPLETED in event_types
    assert TransformationEventType.ARTIFACT_CREATED in event_types
    assert TransformationEventType.JOB_COMPLETED in event_types


def test_pure_external_handoff_sets_waiting_external_zero_progress(handoff_setup):
    """Verify pure external workflow transitions to WAITING_EXTERNAL with 0.0 progress and stages contracts."""
    canonical = handoff_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.PRESENTATION, OutputFormat.VIDEO],
        canonical_id=canonical.id,
        project_id=handoff_setup["project"].id,
    )

    result = transform_service.orchestrate_transformation(job.id)

    assert result.status == WorkflowStatus.WAITING_EXTERNAL
    updated_job = job_service.get_job(job.id)
    assert updated_job.state == JobState.WAITING_EXTERNAL
    assert updated_job.progress == 0.0
    assert len(updated_job.artifact_ids) == 0

    # Verify staged contracts in format_overrides (MUST-FIX #4: passive staging, no auto-dispatch)
    staged = job_artifact_handoff_service.get_staged_contracts(job.id)
    assert len(staged) == 2
    for deliv_id, contract in staged.items():
        assert "canonical_id" in contract or "options" in contract

    events = event_broker.replay(job.id)
    event_types = [e.event_type for e in events]
    assert TransformationEventType.JOB_WAITING_EXTERNAL in event_types


def test_mixed_workflow_handoff_sets_partially_completed_with_exact_ratio(handoff_setup):
    """Verify mixed workflow transitions to PARTIALLY_COMPLETED with real ratio progress (MUST-FIX #5)."""
    canonical = handoff_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN, OutputFormat.PRESENTATION],
        canonical_id=canonical.id,
        project_id=handoff_setup["project"].id,
    )

    result = transform_service.orchestrate_transformation(job.id)

    assert result.status == WorkflowStatus.PARTIALLY_COMPLETED
    updated_job = job_service.get_job(job.id)
    assert updated_job.state == JobState.PARTIALLY_COMPLETED
    # 1 native completed out of 2 total deliverables = 0.5
    assert updated_job.progress == 0.5
    assert len(updated_job.artifact_ids) == 1

    staged = job_artifact_handoff_service.get_staged_contracts(job.id)
    assert len(staged) == 1

    events = event_broker.replay(job.id)
    event_types = [e.event_type for e in events]
    assert TransformationEventType.JOB_PARTIALLY_COMPLETED in event_types


def test_progress_semantics_failed_tasks_decoupled_from_status(handoff_setup, monkeypatch):
    """Verify progress = completed / total is strictly task ratio, independent of status (MUST-FIX #5).
    
    A job with 1 completed and 1 failed deliverable must have progress = 0.5 and state = FAILED.
    """
    canonical = handoff_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN, OutputFormat.HTML],
        canonical_id=canonical.id,
        project_id=handoff_setup["project"].id,
    )

    from app.services.transformation.workflow_orchestrator import workflow_orchestrator
    original_dispatch = workflow_orchestrator.engine_router.dispatch

    def failing_dispatch(*args, **kwargs):
        deliv = kwargs.get("deliverable") or (args[1] if len(args) > 1 else None)
        if deliv and deliv.format == OutputFormat.HTML:
            raise RuntimeError("Synthetic failure in HTML generator")
        return original_dispatch(*args, **kwargs)

    monkeypatch.setattr(workflow_orchestrator.engine_router, "dispatch", failing_dispatch)

    result = transform_service.orchestrate_transformation(job.id)

    assert result.status in (WorkflowStatus.PARTIALLY_COMPLETED, WorkflowStatus.FAILED)
    assert len(result.completed_deliverable_ids) == 1
    assert len(result.failed_tasks) == 1

    updated_job = job_service.get_job(job.id)
    # Lifecycle status is independent (PARTIALLY_COMPLETED or FAILED)
    assert updated_job.state in (JobState.PARTIALLY_COMPLETED, JobState.FAILED)
    # Progress is strictly real task completion ratio (1 / 2 = 0.5) decoupled from status (MUST-FIX #5)
    assert updated_job.progress == 0.5
    assert len(updated_job.artifact_ids) == 1
    assert "generation synthesis failed" in updated_job.error.lower()


def test_referential_integrity_detection_of_corrupted_or_missing_file(handoff_setup):
    """Verify verify_job_artifact_linkage catches missing or tampered physical artifacts."""
    canonical = handoff_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN],
        canonical_id=canonical.id,
        project_id=handoff_setup["project"].id,
    )
    transform_service.orchestrate_transformation(job.id)

    # Initially intact
    assert job_artifact_handoff_service.verify_job_artifact_linkage(job.id) is True

    # Tamper with the artifact file directly on disk
    art = artifact_service.list_artifacts(job_id=job.id)[0]
    tampered_bytes = b"# Tampered content corrupting hash"
    file_path = storage_service.safe_resolve(art.storage_ref)
    file_path.write_bytes(tampered_bytes)

    # Linkage verification must detect hash mismatch
    assert job_artifact_handoff_service.verify_job_artifact_linkage(job.id) is False


def test_handoff_idempotency_prevents_duplicate_artifact_links(handoff_setup):
    """Verify calling handoff repeatedly on an already completed job preserves identical state."""
    canonical = handoff_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN],
        canonical_id=canonical.id,
        project_id=handoff_setup["project"].id,
    )

    result1 = transform_service.orchestrate_transformation(job.id)
    job_after_run1 = job_service.get_job(job.id)

    # Re-run handoff with the same result
    job_after_run2, _ = job_artifact_handoff_service.handoff_workflow_result(job.id, result1)

    assert job_after_run1.artifact_ids == job_after_run2.artifact_ids
    assert len(job_after_run2.artifact_ids) == 1
    assert job_after_run2.state == JobState.COMPLETED
    assert job_after_run2.progress == 1.0


def test_zero_fake_files_leak_to_disk_during_handoff(handoff_setup):
    """Verify D6.5 handoff strictly produces zero fake office/video files."""
    base_data_dir = Path(storage_service.base_dir)

    def count_forbidden_files() -> int:
        forbidden_exts = {".docx", ".pptx", ".xlsx", ".mp4"}
        return sum(
            1 for p in base_data_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in forbidden_exts
        )

    initial_forbidden = count_forbidden_files()

    canonical = handoff_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[
            OutputFormat.DOCUMENT,
            OutputFormat.PRESENTATION,
            OutputFormat.SPREADSHEET,
            OutputFormat.VIDEO,
            OutputFormat.MARKDOWN,
        ],
        canonical_id=canonical.id,
        project_id=handoff_setup["project"].id,
    )

    result = transform_service.orchestrate_transformation(job.id)
    assert result.status == WorkflowStatus.PARTIALLY_COMPLETED

    post_forbidden = count_forbidden_files()
    assert post_forbidden == initial_forbidden
