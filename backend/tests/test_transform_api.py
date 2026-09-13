"""Integration tests for Phase D3.10: /api/v1/transform REST API contracts."""

from fastapi.testclient import TestClient
import pytest

from app.main import app


@pytest.fixture
def client():
    """FastAPI TestClient with initialized database and storage."""
    with TestClient(app) as test_client:
        yield test_client


def test_transform_contract_with_sources_and_prompt(client: TestClient) -> None:
    """Verify /api/v1/transform creates an explicit queued contract without fake generation."""
    # 1. Create project
    proj_res = client.post("/api/v1/projects", json={"name": "Transform Test Project"})
    assert proj_res.status_code == 201
    proj_id = proj_res.json()["id"]

    # 2. Ingest raw text source
    src_res = client.post("/api/v1/sources/text", json={
        "name": "Market Research",
        "text": "Enterprise cloud telemetry expanded 28% in Q2.",
        "project_id": proj_id,
    })
    assert src_res.status_code == 201
    src_id = src_res.json()["id"]

    # 3. Submit transformation request contract
    transform_payload = {
        "requested_formats": ["presentation", "summary"],
        "source_ids": [src_id],
        "prompt": "Synthesize a 10-slide executive deck highlighting revenue growth",
        "project_id": proj_id,
        "configuration": {
            "audience": "Executive",
            "tone": "Authoritative",
            "presentation": {
                "slide_count": 10,
                "theme": "corporate_dark",
            }
        }
    }
    res = client.post("/api/v1/transform", json=transform_payload)
    assert res.status_code == 201
    job_data = res.json()

    # Verify contract fields
    assert job_data["id"].startswith("job_")
    assert job_data["prompt"] == "Synthesize a 10-slide executive deck highlighting revenue growth"
    assert job_data["source_ids"] == [src_id]
    assert job_data["state"] == "queued"
    assert job_data["progress"] == 0.0
    assert job_data["current_stage"] == "Queued for execution"
    assert job_data["artifact_ids"] == []  # Zero fake artifacts!
    job_id = job_data["id"]

    # 4. Get transform status
    status_res = client.get(f"/api/v1/transform/{job_id}")
    assert status_res.status_code == 200
    assert status_res.json()["id"] == job_id
    assert status_res.json()["state"] == "queued"

    # 5. List transform contracts
    list_res = client.get(f"/api/v1/transform?project_id={proj_id}")
    assert list_res.status_code == 200
    assert any(j["id"] == job_id for j in list_res.json())


def test_transform_contract_with_inline_content(client: TestClient) -> None:
    """Verify inline_content is safely ingested as a text source and linked."""
    proj_res = client.post("/api/v1/projects", json={"name": "Inline Transform Project"})
    proj_id = proj_res.json()["id"]

    payload = {
        "requested_formats": ["advisory"],
        "prompt": "Assess vulnerability impact",
        "inline_content": "CVE-2026-1192 allows unauthorized privilege escalation on kernel 6.12.",
        "project_id": proj_id,
    }
    res = client.post("/api/v1/transform", json=payload)
    assert res.status_code == 201
    job_data = res.json()
    assert len(job_data["source_ids"]) == 1
    linked_src_id = job_data["source_ids"][0]
    assert linked_src_id.startswith("src_")

    # Verify the source physically exists in the database
    src_res = client.get(f"/api/v1/sources/{linked_src_id}")
    assert src_res.status_code == 200
    assert "CVE-2026-1192" in client.get(f"/api/v1/sources/{linked_src_id}/download").text


def test_transform_contract_with_prompt_only(client: TestClient) -> None:
    """Verify transform request can be initiated directly with a chat prompt/topic without prior sources."""
    payload = {
        "requested_formats": ["summary"],
        "prompt": "Explain the architectural difference between reactive and proactive agents",
    }
    res = client.post("/api/v1/transform", json=payload)
    assert res.status_code == 201
    job_data = res.json()
    assert job_data["prompt"] == "Explain the architectural difference between reactive and proactive agents"
    assert job_data["source_ids"] == []
    assert job_data["state"] == "queued"


def test_transform_rejects_empty_inputs(client: TestClient) -> None:
    """Verify transform request is rejected if neither source_ids nor prompt/inline content is given."""
    payload = {
        "requested_formats": ["presentation"],
        "source_ids": [],
        "prompt": None,
        "inline_content": None,
    }
    res = client.post("/api/v1/transform", json=payload)
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "BAD_REQUEST"
