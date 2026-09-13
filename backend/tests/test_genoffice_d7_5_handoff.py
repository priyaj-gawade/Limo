"""Tests for GenOffice Artifact Handoff, Storage Ingestion, Endpoints, and Chat Hydration (Phase D7.5)."""

from datetime import datetime, timezone
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.exceptions import StorageError
from app.models.enums import ArtifactType, FeatureMode, JobState, MessageRole, OutputFormat
from app.models.generation_config import GenerationConfig
from app.models.job import TransformationJob
from app.models.transformation_events import TransformationEventType
from app.services.artifact_service import artifact_service
from app.services.chat_service import chat_service
from app.services.job_service import job_service
from app.services.project_service import project_service
from app.services.transformation.event_broker import event_broker
from app.services.transformation.genoffice_client import genoffice_client
from app.services.transformation.handoff import job_artifact_handoff_service
from app.storage.service import storage_service


@pytest.fixture
def d7_5_environment(tmp_path):
    """Set up project, job, and test files for D7.5 handoff tests."""
    project = project_service.create_project(
        name="D7.5 Verification Project",
        description="Testing GenOffice handoff to Limo",
    )

    job = job_service.create_job(
        project_id=project.id,
        session_id=None,
        requested_formats=[OutputFormat.DOCUMENT],
        configuration=GenerationConfig(),
    )

    # Create dummy native document and thumbnail
    native_doc = tmp_path / "Financial_Summary.docx"
    doc_content = b"PK\x03\x04Real docx content bytes for testing"
    native_doc.write_bytes(doc_content)

    native_thumb = tmp_path / "Financial_Summary.docx.thumb.png"
    thumb_content = b"\x89PNG\r\n\x1a\nFake PNG thumbnail data"
    native_thumb.write_bytes(thumb_content)

    return {
        "project": project,
        "job": job,
        "doc_path": str(native_doc),
        "thumb_path": str(native_thumb),
        "doc_bytes": doc_content,
        "thumb_bytes": thumb_content,
    }


def test_handoff_genoffice_artifact_success(d7_5_environment):
    """Verify GenOffice artifact ingestion copies bytes into sandboxed storage, registers Artifact, and emits events."""
    job = d7_5_environment["job"]
    doc_path = d7_5_environment["doc_path"]
    thumb_path = d7_5_environment["thumb_path"]

    captured_events = []
    event_broker.subscribe(job.id, lambda e: captured_events.append(e))

    artifact = job_artifact_handoff_service.handoff_genoffice_artifact(
        job_id=job.id,
        genoffice_job_id="genoffice_job_123",
        genoffice_artifact={
            "file_path": doc_path,
            "format": ".docx",
            "title": "Financial Summary",
            "thumbnail_path": thumb_path,
        },
    )

    assert artifact is not None
    assert artifact.id.startswith("art_")
    assert artifact.title == "Financial Summary"
    assert artifact.artifact_type == ArtifactType.DOC
    assert artifact.file_format == ".docx"
    assert artifact.size_bytes == len(d7_5_environment["doc_bytes"])
    assert artifact.content_hash == storage_service.compute_sha256(d7_5_environment["doc_bytes"])

    # Verify sandboxed storage persistence
    assert storage_service.file_exists(artifact.storage_ref)
    stored_bytes = storage_service.read_file(artifact.storage_ref)
    assert stored_bytes == d7_5_environment["doc_bytes"]

    # Verify thumbnail ingested into storage
    assert "thumbnail_storage_ref" in artifact.metadata
    thumb_ref = artifact.metadata["thumbnail_storage_ref"]
    assert storage_service.file_exists(thumb_ref)
    stored_thumb = storage_service.read_file(thumb_ref)
    assert stored_thumb == d7_5_environment["thumb_bytes"]

    # Verify living native path recorded
    assert artifact.metadata["genoffice_file_path"] == str(Path(doc_path).resolve())
    assert artifact.metadata["genoffice_job_id"] == "genoffice_job_123"

    # Verify job linkage
    updated_job = job_service.get_job(job.id)
    assert artifact.id in updated_job.artifact_ids

    # Verify lifecycle event emitted
    artifact_events = [e for e in captured_events if e.event_type == TransformationEventType.ARTIFACT_CREATED]
    assert len(artifact_events) == 1
    assert artifact_events[0].payload["artifact_id"] == artifact.id
    assert artifact_events[0].payload["thumbnail_available"] is True


def test_handoff_genoffice_artifact_idempotency(d7_5_environment):
    """Verify repeated handoff of the same file content returns the existing artifact without creating duplicates."""
    job = d7_5_environment["job"]
    doc_path = d7_5_environment["doc_path"]

    art1 = job_artifact_handoff_service.handoff_genoffice_artifact(
        job_id=job.id,
        genoffice_job_id="genoffice_job_123",
        genoffice_artifact={"file_path": doc_path, "format": ".docx"},
    )

    art2 = job_artifact_handoff_service.handoff_genoffice_artifact(
        job_id=job.id,
        genoffice_job_id="genoffice_job_123",
        genoffice_artifact={"file_path": doc_path, "format": ".docx"},
    )

    assert art1.id == art2.id
    artifacts_for_job = artifact_service.list_artifacts(job_id=job.id)
    assert len(artifacts_for_job) == 1


def test_handoff_genoffice_artifact_missing_file(d7_5_environment):
    """Verify non-existent file path raises StorageError."""
    job = d7_5_environment["job"]

    with pytest.raises(StorageError) as exc:
        job_artifact_handoff_service.handoff_genoffice_artifact(
            job_id=job.id,
            genoffice_job_id="genoffice_job_999",
            genoffice_artifact={"file_path": "C:\\nonexistent\\path\\doc.docx"},
        )
    assert "does not exist on disk" in str(exc.value)


def test_artifact_thumbnail_endpoint(client: TestClient, d7_5_environment):
    """Verify GET /api/v1/artifacts/{id}/thumbnail serves image/png with caching headers."""
    job = d7_5_environment["job"]
    doc_path = d7_5_environment["doc_path"]
    thumb_path = d7_5_environment["thumb_path"]

    artifact = job_artifact_handoff_service.handoff_genoffice_artifact(
        job_id=job.id,
        genoffice_job_id="genoffice_job_456",
        genoffice_artifact={
            "file_path": doc_path,
            "format": ".docx",
            "thumbnail_path": thumb_path,
        },
    )

    res = client.get(f"/api/v1/artifacts/{artifact.id}/thumbnail")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert "Cache-Control" in res.headers
    assert res.content == d7_5_environment["thumb_bytes"]


def test_artifact_thumbnail_404_when_missing(client: TestClient, d7_5_environment, tmp_path):
    """Verify GET /api/v1/artifacts/{id}/thumbnail returns 404 if no thumbnail was captured."""
    job = d7_5_environment["job"]

    # File without thumbnail
    no_thumb_doc = tmp_path / "NoThumb.xlsx"
    no_thumb_doc.write_bytes(b"Spreadsheet data without thumbnail")

    artifact = job_artifact_handoff_service.handoff_genoffice_artifact(
        job_id=job.id,
        genoffice_job_id="genoffice_job_789",
        genoffice_artifact={"file_path": str(no_thumb_doc), "format": ".xlsx"},
    )

    res = client.get(f"/api/v1/artifacts/{artifact.id}/thumbnail")
    assert res.status_code == 404


def test_artifact_download_endpoint(client: TestClient, d7_5_environment):
    """Verify GET /api/v1/artifacts/{id}/download returns file content with attachment header."""
    job = d7_5_environment["job"]
    doc_path = d7_5_environment["doc_path"]

    artifact = job_artifact_handoff_service.handoff_genoffice_artifact(
        job_id=job.id,
        genoffice_job_id="genoffice_job_101",
        genoffice_artifact={"file_path": doc_path, "format": ".docx", "title": "Quarterly Report"},
    )

    res = client.get(f"/api/v1/artifacts/{artifact.id}/download")
    assert res.status_code == 200
    assert res.content == d7_5_environment["doc_bytes"]
    assert 'attachment; filename="Quarterly_Report.docx"' in res.headers["content-disposition"]


@pytest.mark.asyncio
async def test_artifact_open_endpoint(client: TestClient, d7_5_environment, monkeypatch):
    """Verify POST /api/v1/artifacts/{id}/open invokes GenOffice automation client."""
    job = d7_5_environment["job"]
    doc_path = d7_5_environment["doc_path"]

    artifact = job_artifact_handoff_service.handoff_genoffice_artifact(
        job_id=job.id,
        genoffice_job_id="genoffice_job_202",
        genoffice_artifact={"file_path": doc_path, "format": ".docx"},
    )

    async def mock_open_file(file_path: str):
        return {
            "status": "opened",
            "method": "loopback_http",
            "file_path": file_path,
        }

    monkeypatch.setattr(genoffice_client, "open_file", mock_open_file)

    res = client.post(f"/api/v1/artifacts/{artifact.id}/open")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "opened"
    assert data["artifact_id"] == artifact.id
    assert data["details"]["method"] == "loopback_http"


def test_chat_history_artifacts_hydration(client: TestClient, d7_5_environment):
    """Verify GET /api/v1/chats/{session_id}/messages resolves artifact records and execution summary."""
    job = d7_5_environment["job"]
    doc_path = d7_5_environment["doc_path"]

    artifact = job_artifact_handoff_service.handoff_genoffice_artifact(
        job_id=job.id,
        genoffice_job_id="genoffice_job_303",
        genoffice_artifact={"file_path": doc_path, "format": ".docx", "title": "Budget Proposal"},
    )

    session = chat_service.create_session(title="Financial Review", mode=FeatureMode.DOCS)
    chat_service.add_assistant_message(
        session_id=session.id,
        content="Here is the generated budget proposal.",
        artifact_ids=[artifact.id],
        execution_summary="Generated 4-page executive budget proposal using native GenOffice document synthesis.",
    )

    res = client.get(f"/api/v1/chats/{session.id}/messages")
    assert res.status_code == 200
    messages = res.json()
    assert len(messages) == 1
    msg = messages[0]
    assert msg["role"] == "assistant"
    assert msg["execution_summary"] == "Generated 4-page executive budget proposal using native GenOffice document synthesis."
    assert len(msg["artifacts"]) == 1
    art_payload = msg["artifacts"][0]
    assert art_payload["id"] == artifact.id
    assert art_payload["title"] == "Budget Proposal"
    assert art_payload["file_format"] == ".docx"
