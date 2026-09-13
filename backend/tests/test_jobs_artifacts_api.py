"""Integration tests for Jobs and Artifacts REST API endpoints."""

from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.storage.service import storage_service


@pytest.fixture
def client():
    """FastAPI TestClient with initialized storage and database."""
    with TestClient(app) as test_client:
        yield test_client


def test_jobs_api_flow(client: TestClient) -> None:
    """Verify Jobs REST endpoints: create, list, get, cancel."""
    # 1. Create project and chat session
    proj_res = client.post("/api/v1/projects", json={"name": "Jobs API Test Project"})
    assert proj_res.status_code == 201
    proj_id = proj_res.json()["id"]

    chat_res = client.post("/api/v1/chats", json={"title": "Jobs Test Chat", "project_id": proj_id})
    assert chat_res.status_code == 201
    chat_id = chat_res.json()["id"]

    # 2. Create Job via consolidated /transform endpoint
    job_payload = {
        "requested_formats": ["presentation", "summary"],
        "prompt": "Synthesize presentation and summary",
        "project_id": proj_id,
        "session_id": chat_id,
        "configuration": {
            "audience": "Executive",
            "tone": "Authoritative",
        },
    }
    create_res = client.post("/api/v1/transform", json=job_payload)

    assert create_res.status_code == 201
    job_data = create_res.json()
    assert job_data["id"].startswith("job_")
    assert job_data["state"] == "queued"
    assert job_data["progress"] == 0.0
    assert "presentation" in job_data["requested_formats"]
    job_id = job_data["id"]

    # 3. Get Job
    get_res = client.get(f"/api/v1/jobs/{job_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == job_id

    # 4. List Jobs with filter
    list_res = client.get(f"/api/v1/jobs?project_id={proj_id}")
    assert list_res.status_code == 200
    assert any(j["id"] == job_id for j in list_res.json())

    # 5. Cancel Job
    cancel_res = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["state"] == "cancelled"

    # 6. Attempting to cancel already cancelled job -> 400 Bad Request
    recancel_res = client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert recancel_res.status_code == 400


def test_artifacts_api_flow(client: TestClient) -> None:
    """Verify Artifacts REST endpoints: register, download, versioning, validation, and provenance."""
    # Create parent project
    proj_res = client.post("/api/v1/projects", json={"name": "Artifacts API Test Project"})
    proj_id = proj_res.json()["id"]

    # 1. Attempt to register without physical file -> 500/StorageError
    bad_reg_payload = {
        "title": "Missing File Deck",
        "artifact_type": "slide",
        "file_format": ".pptx",
        "storage_ref": "artifacts/non_existent/file.pptx",
        "project_id": proj_id,
    }
    bad_res = client.post("/api/v1/artifacts", json=bad_reg_payload)
    assert bad_res.status_code == 500
    assert "StorageError" in bad_res.json()["error"]["message"] or "does not exist" in bad_res.json()["error"]["message"]

    # 2. Write real file to sandboxed storage first
    raw_bytes = b"PK\x03\x04Real PowerPoint Slides Presentation"
    storage_ref, size, content_hash = storage_service.save_artifact_file(
        artifact_id="art_api_test",
        filename="presentation.pptx",
        content=raw_bytes,
    )

    # 3. Register real artifact
    reg_payload = {
        "title": "Board Presentation Q4",
        "artifact_type": "slide",
        "file_format": "pptx",
        "storage_ref": storage_ref,
        "project_id": proj_id,
        "stats": "15 Slides • 16:9",
    }
    reg_res = client.post("/api/v1/artifacts", json=reg_payload)
    assert reg_res.status_code == 201
    art_data = reg_res.json()
    art_id = art_data["id"]
    assert art_data["content_hash"] == content_hash
    assert art_data["size_bytes"] == size
    assert art_data["version"] == 1

    # 4. Get artifact
    get_res = client.get(f"/api/v1/artifacts/{art_id}")
    assert get_res.status_code == 200
    assert get_res.json()["title"] == "Board Presentation Q4"

    # 5. List artifacts
    list_res = client.get(f"/api/v1/artifacts?project_id={proj_id}")
    assert list_res.status_code == 200
    assert any(a["id"] == art_id for a in list_res.json())

    # 6. Download binary
    down_res = client.get(f"/api/v1/artifacts/{art_id}/download")
    assert down_res.status_code == 200
    assert down_res.content == raw_bytes

    # 7. Create version snapshot (requires real revision file)
    v2_bytes = b"PK\x03\x04Real PowerPoint Slides Presentation V2 Updated"
    ref_v2, _, hash_v2 = storage_service.save_artifact_file(
        artifact_id="art_api_test",
        filename="presentation_v2.pptx",
        content=v2_bytes,
    )
    ver_res = client.post(
        f"/api/v1/artifacts/{art_id}/versions",
        json={"storage_ref": ref_v2, "change_summary": "Revised slides 3-5"},
    )
    assert ver_res.status_code == 201
    ver_data = ver_res.json()
    assert ver_data["version_number"] == 2
    assert ver_data["content_hash"] == hash_v2

    # Verify parent artifact updated to version 2
    art_updated = client.get(f"/api/v1/artifacts/{art_id}").json()
    assert art_updated["version"] == 2

    # 8. Record validation report
    val_payload = {
        "is_valid": True,
        "score": 0.88,
        "hallucination_check_passed": True,
        "citations_verified": [
            {
                "claim": "Revenue grew by 24%",
                "source_id": "src_123",
                "source_hash": "f" * 64,
                "citation_text": "Revenue grew 24% YoY",
                "similarity_score": 0.95,
            }
        ],
        "warnings": [],
        "errors": [],
    }
    val_res = client.post(f"/api/v1/artifacts/{art_id}/validation", json=val_payload)
    assert val_res.status_code == 201
    assert val_res.json()["is_valid"] is True
    assert val_res.json()["score"] == 0.88

    # 9. Record provenance ledger entry
    prov_payload = {
        "source_hashes": ["f" * 64],
        "generator_name": "GenOffice.SlideDeckGenerator",
        "model_version": "gemini-3.5-flash-lite",
        "canonical_content_hash": "e" * 64,
    }
    prov_res = client.post(f"/api/v1/artifacts/{art_id}/provenance", json=prov_payload)
    assert prov_res.status_code == 201
    prov_data = prov_res.json()
    assert prov_data["artifact_id"] == art_id
    assert prov_data["generator_name"] == "GenOffice.SlideDeckGenerator"
