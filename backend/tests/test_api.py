"""Integration tests for Phase D3.5 & D3.6 FastAPI REST endpoints."""

import io
from fastapi.testclient import TestClient
import pytest

from app.main import app


@pytest.fixture
def client():
    """FastAPI TestClient with initialized database and storage."""
    with TestClient(app) as test_client:
        yield test_client


def test_projects_api_flow(client: TestClient) -> None:
    """Verify Projects REST endpoints: create, get, list, patch, delete."""
    # 1. Create project
    create_payload = {
        "name": "Integration Project",
        "description": "Integration test for REST endpoints",
        "metadata": {"test": True},
    }
    res = client.post("/api/v1/projects", json=create_payload)
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Integration Project"
    proj_id = data["id"]

    # 2. Get project
    res = client.get(f"/api/v1/projects/{proj_id}")
    assert res.status_code == 200
    assert res.json()["id"] == proj_id

    # 3. List projects
    res = client.get("/api/v1/projects")
    assert res.status_code == 200
    assert any(p["id"] == proj_id for p in res.json())

    # 4. Patch project
    patch_payload = {"name": "Updated Project Name"}
    res = client.patch(f"/api/v1/projects/{proj_id}", json=patch_payload)
    assert res.status_code == 200
    assert res.json()["name"] == "Updated Project Name"

    # 5. Delete project
    res = client.delete(f"/api/v1/projects/{proj_id}")
    assert res.status_code == 204

    # 6. Verify 404
    res = client.get(f"/api/v1/projects/{proj_id}")
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "ENTITY_NOT_FOUND"


def test_sources_api_flow(client: TestClient) -> None:
    """Verify Sources REST endpoints: multipart upload, text creation, download, list, delete."""
    # Create parent project
    proj_res = client.post("/api/v1/projects", json={"name": "Source Test Project"})
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # 1. Upload source file
    file_bytes = b"Sample CSV raw payload\na,b,c\n1,2,3"
    files = {"file": ("data.csv", io.BytesIO(file_bytes), "text/csv")}
    upload_res = client.post(
        "/api/v1/sources/upload",
        files=files,
        data={"project_id": project_id},
    )
    assert upload_res.status_code == 201
    src_data = upload_res.json()
    source_id = src_data["id"]
    assert src_data["name"] == "data.csv"
    assert src_data["size_bytes"] == len(file_bytes)

    # 2. Create text source
    text_res = client.post(
        "/api/v1/sources/text",
        json={
            "name": "incident_memo",
            "text": "Critical vulnerability discovered in auth service.",
            "project_id": project_id,
        },
    )
    assert text_res.status_code == 201
    text_source_id = text_res.json()["id"]

    # 3. List sources by project
    list_res = client.get(f"/api/v1/sources?project_id={project_id}")
    assert list_res.status_code == 200
    sources = list_res.json()
    assert len(sources) == 2
    assert any(s["id"] == source_id for s in sources)
    assert any(s["id"] == text_source_id for s in sources)

    # 4. Download source raw content (GET request as documented)
    dl_res = client.get(f"/api/v1/sources/{source_id}/download")
    assert dl_res.status_code == 200
    assert dl_res.content == file_bytes

    # 5. Delete source
    del_res = client.delete(f"/api/v1/sources/{source_id}")
    assert del_res.status_code == 204

    # 6. Verify 404
    get_res = client.get(f"/api/v1/sources/{source_id}")
    assert get_res.status_code == 404


def test_chats_api_flow(client: TestClient) -> None:
    """Verify Chats and Messages REST endpoints: create, list, patch, message addition, history."""
    # 1. Create chat session
    create_res = client.post("/api/v1/chats", json={"title": "Analysis Thread", "mode": "docs"})
    assert create_res.status_code == 201
    session_id = create_res.json()["id"]

    # 2. List sessions
    list_res = client.get("/api/v1/chats")
    assert list_res.status_code == 200
    assert any(c["id"] == session_id for c in list_res.json())

    # 3. Add user message
    user_msg_res = client.post(
        f"/api/v1/chats/{session_id}/messages",
        json={
            "role": "user",
            "content": "Please synthesize the incident timeline.",
        },
    )
    assert user_msg_res.status_code == 201
    assert user_msg_res.json()["role"] == "user"

    # 4. Add assistant message
    asst_msg_res = client.post(
        f"/api/v1/chats/{session_id}/messages",
        json={
            "role": "assistant",
            "content": "Here is the verified incident chronology.",
            "execution_summary": "Extracted 4 timeline events.",
        },
    )
    assert asst_msg_res.status_code == 201
    assert asst_msg_res.json()["role"] == "assistant"

    # 5. Retrieve history
    history_res = client.get(f"/api/v1/chats/{session_id}/messages")
    assert history_res.status_code == 200
    messages = history_res.json()
    assert len(messages) == 2
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"

    # 6. Rename session
    rename_res = client.patch(
        f"/api/v1/chats/{session_id}",
        json={"title": "Updated Analysis Thread"},
    )
    assert rename_res.status_code == 200
    assert rename_res.json()["title"] == "Updated Analysis Thread"

    # 7. Delete session
    del_res = client.delete(f"/api/v1/chats/{session_id}")
    assert del_res.status_code == 204

    # 8. Verify session 404
    get_res = client.get(f"/api/v1/chats/{session_id}")
    assert get_res.status_code == 404
