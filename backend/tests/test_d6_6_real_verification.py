"""Comprehensive End-to-End Verification Test Suite for Phase D6.6.

Verifies the complete D6 transformation pipeline:
D5 CanonicalContent
  -> D6.1 Request + Configuration
  -> D6.2 Output Plan + Routing
  -> D6.3 Contracts / Native Adapters
  -> D6.4 Workflow Orchestration
  -> D6.5 Job + Artifact Handoff
  -> Final verified state

Covers all 7 verification categories required for Phase D6 closure:
1. Native Deliverables (Markdown, HTML, LinkedIn, Twitter, Infographic)
2. External Deliverables (DOCX, PPTX, XLSX, PDF, VIDEO)
3. Mixed Workflow (Native execution + External contract staging)
4. Failure Handling & Cancellation
5. Job & Artifact Referential Integrity
6. Lifecycle Event Integrity & Zero-Leakage Sanitization
7. Regression & Zero-Fake Deliverables Guarantee
"""

import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import pytest

from app.exceptions import BadRequestError, EntityNotFoundError, InvalidStateError, UnimplementedEngineError
from app.models.content import CanonicalContent, CanonicalDataPoint, CanonicalFact, CanonicalIntent
from app.models.enums import JobState, OutputFormat
from app.models.transformation_events import TransformationEventType
from app.models.workflow import TaskStatus, WorkflowStatus
from app.services.artifact_service import artifact_service
from app.services.job_service import job_service
from app.services.project_service import project_service
from app.services.source_service import source_service
from app.services.transform_service import transform_service
from app.services.transformation.event_broker import event_broker, sanitize_public_payload
from app.services.transformation.handoff import job_artifact_handoff_service
from app.services.transformation.workflow_orchestrator import workflow_orchestrator
from app.storage.service import storage_service


@pytest.fixture
def real_d5_canonical_setup():
    """Setup realistic project, source, and verified D5 CanonicalContent intermediate."""
    project = project_service.create_project(
        name="D6.6 Enterprise Verification Project",
        description="End-to-end verification of transformation pipeline",
    )
    source_text = (
        "# Global Infrastructure & Resilience Audit\n\n"
        "## Executive Telemetry\n"
        "Our edge routing topology successfully processed 4.8B packets in Q3 2026.\n"
        "Zero data breaches occurred across all 14 multi-region clusters.\n"
        "Failover latency averaged 42ms during simulated node disruptions.\n\n"
        "## Strategic Recommendations\n"
        "1. Migrate legacy cold-storage pipelines to real-time event-driven replication.\n"
        "2. Automate canary validation across global DNS ingress nodes.\n"
    )
    src = source_service.register_text_source(
        name="infrastructure_audit_report.txt",
        text_content=source_text,
        project_id=project.id,
    )
    canonical = CanonicalContent(
        source_ids=[src.id],
        title="Global Infrastructure & Resilience Audit",
        context="Quarterly engineering telemetry and system availability audit across multi-region clusters.",
        intent=CanonicalIntent(
            primary_purpose="Provide leadership and engineering teams with verified resilience telemetry",
            target_audiences=["Executive Leadership", "Site Reliability Engineers"],
            core_narrative="Infrastructure maintained 99.99% availability with zero regressions in Q3 2026.",
        ),
        facts=[
            CanonicalFact(
                statement="Edge routing topology processed 4.8B packets in Q3 2026.",
                confidence=0.99,
                evidence_status="verified",
                source_reference="Section 2, Paragraph 1",
            ),
            CanonicalFact(
                statement="Zero data breaches occurred across all 14 multi-region clusters.",
                confidence=0.98,
                evidence_status="verified",
                source_reference="Section 2, Paragraph 2",
            ),
            CanonicalFact(
                statement="Failover latency averaged 42ms during simulated node disruptions.",
                confidence=0.97,
                evidence_status="verified",
                source_reference="Section 2, Paragraph 3",
            ),
        ],
        data_points=[
            CanonicalDataPoint(metric="Processed Packets", value="4.8B", unit="packets", context="Q3 2026"),
            CanonicalDataPoint(metric="Data Breaches", value="0", unit="incidents", context="Multi-region"),
            CanonicalDataPoint(metric="Failover Latency", value="42", unit="milliseconds", context="Disruption tests"),
            CanonicalDataPoint(metric="Cluster Count", value="14", unit="clusters", context="Global"),
        ],
        recommendations=[
            "Migrate legacy cold-storage pipelines to real-time event-driven replication.",
            "Automate canary validation across global DNS ingress nodes.",
        ],
        clean_markdown=source_text,
        content_hash=storage_service.compute_sha256(source_text.encode("utf-8")),
        created_at=datetime.now(timezone.utc),
    )
    saved_canonical = job_service.save_canonical_content(canonical)
    return {
        "project": project,
        "source": src,
        "canonical": saved_canonical,
    }


# ==============================================================================
# Category 1: Native Deliverables (Markdown, HTML, LinkedIn, Twitter, Infographic)
# ==============================================================================

def test_category_1_native_deliverables_e2e_verification(real_d5_canonical_setup):
    """Verify all 5 native deliverables execute in-process and register real verifiable artifacts."""
    canonical = real_d5_canonical_setup["canonical"]
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
        project_id=real_d5_canonical_setup["project"].id,
    )

    result = transform_service.orchestrate_transformation(job.id)

    # 1. WorkflowResult assertions
    assert result.status == WorkflowStatus.COMPLETED
    assert result.total_deliverables == 5
    assert len(result.artifacts) == 5
    assert len(result.completed_deliverable_ids) == 5
    assert len(result.blocked_contracts) == 0
    assert len(result.failed_tasks) == 0

    # 2. Verify physical files and content integrity on disk
    expected_extensions = {
        OutputFormat.MARKDOWN: ".md",
        OutputFormat.HTML: ".html",
        OutputFormat.LINKEDIN: ".md",
        OutputFormat.TWITTER: ".json",
        OutputFormat.INFOGRAPHIC: ".svg",
    }
    produced_extensions = set()
    for art in result.artifacts:
        assert storage_service.file_exists(art.storage_ref)
        raw_bytes = storage_service.read_file(art.storage_ref)
        assert len(raw_bytes) > 0
        assert storage_service.compute_sha256(raw_bytes) == art.content_hash
        assert art.job_id == job.id
        produced_extensions.add(art.file_format)

    assert produced_extensions == set(expected_extensions.values())

    # 3. Verify SQLite Job state and real task-based progress
    persisted_job = job_service.get_job(job.id)
    assert persisted_job.state == JobState.COMPLETED
    assert persisted_job.progress == 1.0
    assert len(persisted_job.artifact_ids) == 5
    assert job_artifact_handoff_service.verify_job_artifact_linkage(job.id) is True

    # 4. Verify ordered lifecycle events
    events = event_broker.replay(job.id)
    assert len(events) >= 13  # 1 created + 1 started + 5*(task_started + task_completed + artifact_created) + 1 completed
    types = [e.event_type for e in events]
    assert types[0] == TransformationEventType.JOB_CREATED
    assert types[1] == TransformationEventType.JOB_STARTED
    assert types[-1] == TransformationEventType.JOB_COMPLETED


# ==============================================================================
# Category 2: External Deliverables (DOCX, PPTX, XLSX, PDF, VIDEO)
# ==============================================================================

def test_category_2_external_deliverables_guarded_and_zero_fake_files(real_d5_canonical_setup):
    """Verify external formats produce typed contracts, WAITING_EXTERNAL, and ZERO fake files on disk."""
    base_data_dir = Path(storage_service.base_dir)

    def count_forbidden_files() -> int:
        forbidden = {".docx", ".pptx", ".xlsx", ".pdf", ".mp4"}
        return sum(
            1 for p in base_data_dir.rglob("*")
            if p.is_file() and p.suffix.lower() in forbidden
        )

    initial_forbidden = count_forbidden_files()
    canonical = real_d5_canonical_setup["canonical"]

    external_formats = [
        OutputFormat.DOCUMENT,
        OutputFormat.PRESENTATION,
        OutputFormat.SPREADSHEET,
        OutputFormat.PDF,
        OutputFormat.VIDEO,
    ]

    job = transform_service.create_transform_contract(
        requested_formats=external_formats,
        canonical_id=canonical.id,
        project_id=real_d5_canonical_setup["project"].id,
    )

    result = transform_service.orchestrate_transformation(job.id)

    # 1. State and result assertions
    assert result.status == WorkflowStatus.WAITING_EXTERNAL
    assert result.total_deliverables == 5
    assert len(result.artifacts) == 0
    assert len(result.blocked_contracts) == 5
    assert len(result.failed_tasks) == 0

    # 2. Verify typed contract payloads contain canonical provenance
    for deliv_id, contract in result.blocked_contracts.items():
        assert "canonical_id" in contract or "options" in contract
        cid = contract.get("canonical_id") or contract.get("options", {}).get("canonical_id")
        assert cid == canonical.id

    # 3. Verify SQLite state reflects WAITING_EXTERNAL and progress = 0.0
    persisted_job = job_service.get_job(job.id)
    assert persisted_job.state == JobState.WAITING_EXTERNAL
    assert persisted_job.progress == 0.0
    assert len(persisted_job.artifact_ids) == 0

    # 4. Zero fake files generated
    post_forbidden = count_forbidden_files()
    assert post_forbidden == initial_forbidden, "Forbidden fake deliverables leaked to filesystem"

    # 5. Direct execution attempt of guarded format raises UnimplementedEngineError
    plan_dict = persisted_job.configuration.format_overrides["output_plan"]
    docx_deliv_id = next(d["deliverable_id"] for d in plan_dict["deliverables"] if d["format"] == "document")
    with pytest.raises(UnimplementedEngineError) as exc_info:
        transform_service.execute_deliverable(deliverable_id=docx_deliv_id, job_id=job.id)
    assert exc_info.value.status_code == 501
    assert "genoffice_docs" in exc_info.value.message


# ==============================================================================
# Category 3: Mixed Workflow (Native Execution + Staged Contracts)
# ==============================================================================

def test_category_3_mixed_workflow_execution_and_staging(real_d5_canonical_setup):
    """Verify mixed workflow completes native deliverables, stages contracts, and sets PARTIALLY_COMPLETED."""
    canonical = real_d5_canonical_setup["canonical"]
    mixed_formats = [
        OutputFormat.MARKDOWN,
        OutputFormat.HTML,
        OutputFormat.PRESENTATION,
        OutputFormat.VIDEO,
    ]

    job = transform_service.create_transform_contract(
        requested_formats=mixed_formats,
        canonical_id=canonical.id,
        project_id=real_d5_canonical_setup["project"].id,
    )

    result = transform_service.orchestrate_transformation(job.id)

    # 1. 2 native completed, 2 external blocked
    assert result.status == WorkflowStatus.PARTIALLY_COMPLETED
    assert result.total_deliverables == 4
    assert len(result.artifacts) == 2
    assert len(result.completed_deliverable_ids) == 2
    assert len(result.blocked_contracts) == 2
    assert len(result.failed_tasks) == 0

    # 2. Check real task ratio progress: 2 / 4 = 0.5
    persisted_job = job_service.get_job(job.id)
    assert persisted_job.state == JobState.PARTIALLY_COMPLETED
    assert persisted_job.progress == 0.5
    assert len(persisted_job.artifact_ids) == 2

    # 3. Retrieve staged contracts passively without auto-dispatch
    staged = job_artifact_handoff_service.get_staged_contracts(job.id)
    assert len(staged) == 2

    # 4. Terminal event emitted
    events = event_broker.replay(job.id)
    assert events[-1].event_type == TransformationEventType.JOB_PARTIALLY_COMPLETED
    assert events[-1].payload["completed_count"] == 2
    assert events[-1].payload["blocked_count"] == 2


# ==============================================================================
# Category 4: Failure Handling & Cancellation
# ==============================================================================

def test_category_4_failure_handling_transient_retries_exhaustion(real_d5_canonical_setup, monkeypatch):
    """Verify native adapter failure retries up to 3 times, records safe user error, and preserves sibling artifacts."""
    canonical = real_d5_canonical_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN, OutputFormat.HTML],
        canonical_id=canonical.id,
        project_id=real_d5_canonical_setup["project"].id,
    )

    original_dispatch = workflow_orchestrator.engine_router.dispatch
    dispatch_attempts = []

    def failing_html_dispatch(*args, **kwargs):
        deliv = kwargs.get("deliverable") or (args[1] if len(args) > 1 else None)
        if deliv and deliv.format == OutputFormat.HTML:
            dispatch_attempts.append(len(dispatch_attempts) + 1)
            raise RuntimeError("Database connection timed out at /var/internal/db.py:99")
        return original_dispatch(*args, **kwargs)

    monkeypatch.setattr(workflow_orchestrator.engine_router, "dispatch", failing_html_dispatch)

    result = transform_service.orchestrate_transformation(job.id)

    # 3 retry attempts executed for HTML
    assert len(dispatch_attempts) == 3
    assert len(result.completed_deliverable_ids) == 1
    assert len(result.failed_tasks) == 1

    # Safe error message sanitization: no internal path or raw traceback
    failed_error = result.failed_tasks[0]["error"]
    assert "Traceback" not in failed_error
    assert "/var/internal" not in failed_error
    assert "Generation synthesis failed" in failed_error

    # Decoupled progress: 1 completed out of 2 = 0.5
    persisted_job = job_service.get_job(job.id)
    assert persisted_job.progress == 0.5
    assert len(persisted_job.artifact_ids) == 1


def test_category_4_cancellation_skips_pending_tasks(real_d5_canonical_setup):
    """Verify workflow cancellation halts execution cleanly and marks pending tasks SKIPPED."""
    canonical = real_d5_canonical_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN, OutputFormat.HTML, OutputFormat.LINKEDIN],
        canonical_id=canonical.id,
        project_id=real_d5_canonical_setup["project"].id,
    )

    from app.models.transformation import OutputPlan
    plan = OutputPlan.model_validate(job.configuration.format_overrides["output_plan"])
    wf = workflow_orchestrator.build_workflow(plan=plan, job_id=job.id)

    # Cancel before execution
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
    assert len(result.completed_deliverable_ids) == 0
    for task in wf.tasks.values():
        assert task.status == TaskStatus.SKIPPED


def test_category_4_missing_canonical_content_raises_not_found(real_d5_canonical_setup):
    """Verify attempting to create a transformation contract with non-existent canonical ID raises EntityNotFoundError."""
    with pytest.raises(EntityNotFoundError) as exc_info:
        transform_service.create_transform_contract(
            requested_formats=[OutputFormat.MARKDOWN],
            canonical_id="can_non_existent_id_9999",
            project_id=real_d5_canonical_setup["project"].id,
        )
    assert "CanonicalContent" in str(exc_info.value)


# ==============================================================================
# Category 5: Job & Artifact Integrity
# ==============================================================================

def test_category_5_job_artifact_linkage_and_idempotency(real_d5_canonical_setup):
    """Verify bidirectional referential integrity, SHA-256 validation, and idempotent re-execution."""
    canonical = real_d5_canonical_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN, OutputFormat.HTML],
        canonical_id=canonical.id,
        project_id=real_d5_canonical_setup["project"].id,
    )

    result1 = transform_service.orchestrate_transformation(job.id)
    assert job_artifact_handoff_service.verify_job_artifact_linkage(job.id) is True

    # Re-executing orchestrate_transformation on already completed job must be idempotent
    result2 = transform_service.orchestrate_transformation(job.id)
    assert [a.id for a in result1.artifacts] == [a.id for a in result2.artifacts]

    persisted_job = job_service.get_job(job.id)
    assert len(persisted_job.artifact_ids) == 2
    assert persisted_job.state == JobState.COMPLETED
    assert persisted_job.progress == 1.0


def test_category_5_terminal_state_protection(real_d5_canonical_setup):
    """Verify that jobs in terminal states cannot be illegally modified back to non-terminal states."""
    canonical = real_d5_canonical_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN],
        canonical_id=canonical.id,
        project_id=real_d5_canonical_setup["project"].id,
    )
    transform_service.orchestrate_transformation(job.id)

    with pytest.raises(InvalidStateError):
        job_service.update_progress(
            job_id=job.id,
            state=JobState.PROCESSING,
            progress=0.1,
        )


# ==============================================================================
# Category 6: Event Integrity & Sanitization
# ==============================================================================

@pytest.mark.asyncio
async def test_category_6_concurrent_event_sequencing_and_sanitization():
    """Verify event sequences are strictly monotonic under concurrency, and zero sensitive data leaks into payloads."""
    job_id = "job_evt_stress_test_001"

    async def emit_sample(i: int):
        await asyncio.sleep(0.001)
        raw_payload = {
            "deliverable_id": f"del_{i}",
            "format": "markdown",
            "api_key": "sk-leak-test-key",
            "chain_of_thought": "Private reasoning step...",
            "system_prompt": "Confidential prompt instructions",
            "traceback": "Traceback: File /app/secret/main.py",
        }
        return event_broker.emit(
            job_id=job_id,
            event_type=TransformationEventType.TASK_STARTED,
            payload=raw_payload,
        )

    # 50 concurrent async emissions
    emitted = await asyncio.gather(*(emit_sample(i) for i in range(50)))
    assert len(emitted) == 50

    seqs = [e.sequence for e in emitted]
    assert len(set(seqs)) == 50
    assert min(seqs) == 1
    assert max(seqs) == 50

    # Verify zero-leakage payload sanitizer
    for e in emitted:
        assert "api_key" not in e.payload
        assert "chain_of_thought" not in e.payload
        assert "system_prompt" not in e.payload
        assert "traceback" not in e.payload
        assert e.payload["deliverable_id"].startswith("del_")


def test_category_6_event_replay_filter():
    """Verify event replay strictly filters by sequence number."""
    job_id = "job_evt_replay_test_002"
    for i in range(15):
        event_broker.emit(job_id, TransformationEventType.TASK_STARTED, {"step": i})

    replayed = event_broker.replay(job_id, after_sequence=10)
    assert len(replayed) == 5
    assert [e.sequence for e in replayed] == [11, 12, 13, 14, 15]


def test_category_4_invalid_format_empty_list_raises_bad_request(real_d5_canonical_setup):
    """Verify attempting to create a transformation contract with empty format list raises BadRequestError."""
    with pytest.raises(BadRequestError, match="At least one target OutputFormat or FeatureMode is required"):
        transform_service.create_transform_contract(
            requested_formats=[],
            canonical_id=real_d5_canonical_setup["canonical"].id,
            project_id=real_d5_canonical_setup["project"].id,
        )


def test_category_4_duplicate_handoff_is_idempotent(real_d5_canonical_setup):
    """Verify calling handoff repeatedly on an already completed job is idempotent and safe."""
    canonical = real_d5_canonical_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN],
        canonical_id=canonical.id,
        project_id=real_d5_canonical_setup["project"].id,
    )
    result = transform_service.orchestrate_transformation(job.id)
    job_before = job_service.get_job(job.id)

    job_after, res_after = job_artifact_handoff_service.handoff_workflow_result(job.id, result)
    assert job_before.artifact_ids == job_after.artifact_ids
    assert job_after.state == JobState.COMPLETED
    assert job_after.progress == 1.0


def test_category_5_progress_ratio_strictly_decoupled_from_status(real_d5_canonical_setup, monkeypatch):
    """Verify progress = completed / total is strictly task ratio, decoupled from status (MUST-FIX #5)."""
    canonical = real_d5_canonical_setup["canonical"]
    job = transform_service.create_transform_contract(
        requested_formats=[OutputFormat.MARKDOWN, OutputFormat.HTML],
        canonical_id=canonical.id,
        project_id=real_d5_canonical_setup["project"].id,
    )

    original_dispatch = workflow_orchestrator.engine_router.dispatch

    def failing_html(*args, **kwargs):
        deliv = kwargs.get("deliverable") or (args[1] if len(args) > 1 else None)
        if deliv and deliv.format == OutputFormat.HTML:
            raise RuntimeError("Synthetic error")
        return original_dispatch(*args, **kwargs)

    monkeypatch.setattr(workflow_orchestrator.engine_router, "dispatch", failing_html)

    result = transform_service.orchestrate_transformation(job.id)
    persisted_job = job_service.get_job(job.id)

    assert persisted_job.progress == 0.5
    assert persisted_job.state in (JobState.PARTIALLY_COMPLETED, JobState.FAILED)
    assert len(persisted_job.artifact_ids) == 1
