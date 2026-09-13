"""Unit tests for Phase D3.7: JobService and TransformationJob contract."""

from pathlib import Path
import pytest

from app.db.init import init_db
from app.exceptions import BadRequestError, EntityNotFoundError, InvalidStateError
from app.models.content import (

    CanonicalContent,
    CanonicalEntity,
    CanonicalFact,
    CanonicalIntent,
)
from app.models.enums import JobState, OutputFormat
from app.models.job import GenerationConfig
from app.services.chat_service import ChatService
from app.services.job_service import JobService
from app.services.project_service import ProjectService


@pytest.fixture
def job_env(tmp_path: Path):
    """Isolated test environment for JobService."""
    db_file = tmp_path / "job_test.db"
    init_db(db_file)

    proj_svc = ProjectService(db_path=str(db_file))
    chat_svc = ChatService(db_path=str(db_file))
    job_svc = JobService(db_path=str(db_file))

    project = proj_svc.create_project(name="Job Test Project")

    return {
        "db_file": db_file,
        "job_svc": job_svc,
        "chat_svc": chat_svc,
        "project": project,
    }



def test_create_and_get_job(job_env) -> None:
    """Verify job creation with default and custom configuration."""
    job_svc: JobService = job_env["job_svc"]
    project = job_env["project"]

    job = job_svc.create_job(
        requested_formats=[OutputFormat.PRESENTATION, OutputFormat.SUMMARY],
        project_id=project.id,
    )
    assert job.id.startswith("job_")
    assert job.project_id == project.id
    assert job.state == JobState.QUEUED
    assert job.progress == 0.0
    assert OutputFormat.PRESENTATION in job.requested_formats
    assert OutputFormat.SUMMARY in job.requested_formats

    fetched = job_svc.get_job(job.id)
    assert fetched.id == job.id
    assert fetched.requested_formats == job.requested_formats


def test_create_job_requires_formats(job_env) -> None:
    """Verify validation when no formats are provided."""
    job_svc: JobService = job_env["job_svc"]
    with pytest.raises(BadRequestError, match="At least one target OutputFormat is required"):
        job_svc.create_job(requested_formats=[])



def test_list_jobs_filtering(job_env) -> None:
    """Verify listing jobs with project, session, and state filters."""
    job_svc: JobService = job_env["job_svc"]
    chat_svc: ChatService = job_env["chat_svc"]
    project = job_env["project"]

    chat1 = chat_svc.create_session(title="Chat Thread 1", project_id=project.id)
    chat2 = chat_svc.create_session(title="Chat Thread 2", project_id=project.id)

    job1 = job_svc.create_job(
        requested_formats=[OutputFormat.VIDEO],
        project_id=project.id,
        session_id=chat1.id,
    )
    job2 = job_svc.create_job(
        requested_formats=[OutputFormat.LINKEDIN],
        project_id=project.id,
        session_id=chat2.id,
    )

    # Filter by project
    jobs = job_svc.list_jobs(project_id=project.id)
    assert len(jobs) == 2

    # Filter by session
    jobs_session_1 = job_svc.list_jobs(session_id=chat1.id)
    assert len(jobs_session_1) == 1
    assert jobs_session_1[0].id == job1.id


    # Filter by state
    jobs_queued = job_svc.list_jobs(state=JobState.QUEUED)
    assert len(jobs_queued) >= 2


def test_job_progress_and_terminal_guard(job_env) -> None:
    """Verify state transitions and terminal state mutation guards."""
    job_svc: JobService = job_env["job_svc"]
    project = job_env["project"]

    job = job_svc.create_job(
        requested_formats=[OutputFormat.PRESENTATION],
        project_id=project.id,
    )

    # 1. Transition to PROCESSING
    updated = job_svc.update_progress(
        job_id=job.id,
        state=JobState.PROCESSING,
        progress=0.45,
        current_stage="Synthesizing Canonical Content",
    )
    assert updated.state == JobState.PROCESSING
    assert updated.progress == 0.45
    assert updated.current_stage == "Synthesizing Canonical Content"

    # 2. Transition to COMPLETED (normalizes progress to 1.0)
    completed = job_svc.update_progress(
        job_id=job.id,
        state=JobState.COMPLETED,
        progress=0.9,  # Should be normalized to 1.0
        current_stage="Deliverable rendered",
        artifact_ids=["art_12345678"],
    )
    assert completed.state == JobState.COMPLETED
    assert completed.progress == 1.0
    assert "art_12345678" in completed.artifact_ids

    # 3. Guard: cannot update completed job
    with pytest.raises(InvalidStateError, match="Cannot update job.*terminal state"):
        job_svc.update_progress(
            job_id=job.id,
            state=JobState.PROCESSING,
            progress=0.5,
        )


def test_job_cancellation_semantics(job_env) -> None:
    """Verify cancelling queued, processing, and terminal jobs."""
    job_svc: JobService = job_env["job_svc"]
    project = job_env["project"]

    # 1. Cancel a queued job (allowed per updated decision)
    job_queued = job_svc.create_job(
        requested_formats=[OutputFormat.SUMMARY],
        project_id=project.id,
    )
    cancelled_queued = job_svc.cancel_job(job_queued.id)
    assert cancelled_queued.state == JobState.CANCELLED

    # 2. Cancel a processing job
    job_proc = job_svc.create_job(
        requested_formats=[OutputFormat.ADVISORY],
        project_id=project.id,
    )
    job_svc.update_progress(job_proc.id, state=JobState.PROCESSING, progress=0.2)
    cancelled_proc = job_svc.cancel_job(job_proc.id)
    assert cancelled_proc.state == JobState.CANCELLED

    # 3. Guard: cannot cancel already cancelled job
    with pytest.raises(InvalidStateError, match="Cannot cancel job.*terminal state"):
        job_svc.cancel_job(job_proc.id)



def test_canonical_content_storage_and_retrieval(job_env) -> None:
    """Verify CanonicalContent intermediate contract persistence."""
    job_svc: JobService = job_env["job_svc"]

    canonical = CanonicalContent(
        source_ids=["src_1", "src_2"],
        title="Executive Briefing",
        context="Annual corporate review",
        intent=CanonicalIntent(
            primary_purpose="Inform leadership",
            target_audiences=["Board of Directors"],
            core_narrative="Revenue grew by 24%",
        ),
        entities=[
            CanonicalEntity(
                name="Limo Project",
                category="ORGANIZATION",
                description="Core platform",
            )
        ],
        facts=[
            CanonicalFact(
                statement="Revenue increased by 24%",
                confidence=1.0,
                supporting_sources=["src_1"],
            )
        ],
        content_hash="a" * 64,
    )

    saved = job_svc.save_canonical_content(canonical)
    assert saved.id == canonical.id

    fetched = job_svc.get_canonical_content(canonical.id)
    assert fetched.id == canonical.id
    assert fetched.title == "Executive Briefing"
    assert len(fetched.facts) == 1
    assert fetched.facts[0].statement == "Revenue increased by 24%"
