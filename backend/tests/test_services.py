"""Tests for Phase D3.5 & D3.6: Business Services (Project, Source, Chat)."""

import hashlib
from pathlib import Path
import time
import pytest

from app.db.init import init_db
from app.exceptions import EntityNotFoundError, StorageError
from app.models.enums import FeatureMode, MessageRole, SourceType
from app.services.chat_service import ChatService
from app.services.project_service import ProjectService
from app.services.source_service import SourceService
from app.storage.service import StorageService


@pytest.fixture
def service_env(tmp_path: Path):
    """Provide clean database and storage environment for service tests."""
    db_file = tmp_path / "services_test.db"
    storage_dir = tmp_path / "data"

    init_db(db_file)
    storage = StorageService(base_dir=storage_dir)
    storage.ensure_directories()

    proj_svc = ProjectService(db_path=str(db_file))
    src_svc = SourceService(db_path=str(db_file), storage=storage)
    chat_svc = ChatService(db_path=str(db_file))

    return {
        "db_file": db_file,
        "storage": storage,
        "proj_svc": proj_svc,
        "src_svc": src_svc,
        "chat_svc": chat_svc,
    }


def test_project_service_lifecycle(service_env) -> None:
    """Verify ProjectService create, read, update, list, and delete."""
    proj_svc: ProjectService = service_env["proj_svc"]

    # 1. Create
    p = proj_svc.create_project(name="Strategic Synthesis", description="Q4 Planning")
    assert p.id.startswith("proj_")
    assert p.name == "Strategic Synthesis"

    # 2. Get
    fetched = proj_svc.get_project(p.id)
    assert fetched.id == p.id
    assert fetched.description == "Q4 Planning"

    # 3. Update
    updated = proj_svc.update_project(p.id, name="Updated Synthesis", description="Revised Q4 Planning")
    assert updated.name == "Updated Synthesis"
    assert updated.description == "Revised Q4 Planning"

    # 4. List
    projects = proj_svc.list_projects()
    assert len(projects) == 1
    assert projects[0].id == p.id

    # 5. Delete
    assert proj_svc.delete_project(p.id) is True
    with pytest.raises(EntityNotFoundError):
        proj_svc.get_project(p.id)


def test_source_service_file_and_text_registration(service_env) -> None:
    """Verify SourceService registers files, verifies physical storage, and serves content."""
    src_svc: SourceService = service_env["src_svc"]
    proj_svc: ProjectService = service_env["proj_svc"]

    project = proj_svc.create_project(name="Telemetry Intake")

    # 1. Register binary file
    payload = b"Sample telemetry payload in CSV format\ncol1,col2\n100,200"
    expected_hash = hashlib.sha256(payload).hexdigest().lower()

    source = src_svc.register_file_source(
        project_id=project.id,
        filename="telemetry.csv",
        content=payload,
        mime_type="text/csv",
    )

    assert source.id.startswith("src_")
    assert source.project_id == project.id
    assert source.size_bytes == len(payload)
    assert source.content_hash == expected_hash
    assert source.source_type == SourceType.TABULAR

    # 2. Read and verify content integrity
    read_bytes = src_svc.read_source_content(source.id)
    assert read_bytes == payload

    # 3. Register raw text snippet
    text_source = src_svc.register_text_source(
        project_id=project.id,
        name="notes",
        text_content="Incident response initial notes.",
    )
    assert text_source.source_type == SourceType.TEXT
    assert text_source.extracted_text == "Incident response initial notes."
    assert src_svc.read_source_content(text_source.id) == b"Incident response initial notes."

    # 4. List sources by project
    sources = src_svc.list_sources(project.id)
    assert len(sources) == 2

    # 5. Delete source safely
    assert src_svc.delete_source(source.id) is True
    with pytest.raises(EntityNotFoundError):
        src_svc.get_source(source.id)


def test_chat_service_messages_and_updated_at_touch(service_env) -> None:
    """Verify ChatService session lifecycle, message chronological order, and updated_at touch."""
    chat_svc: ChatService = service_env["chat_svc"]

    # 1. Create session
    session = chat_svc.create_session(title="Advisory Generation", mode=FeatureMode.DOCS)
    initial_updated_at = session.updated_at

    # Ensure a measurable timestamp tick
    time.sleep(0.01)

    # 2. Add user message
    user_msg = chat_svc.add_user_message(
        session_id=session.id,
        content="Summarize cybersecurity incident findings.",
    )
    assert user_msg.id.startswith("msg_")
    assert user_msg.role == MessageRole.USER
    assert user_msg.content == "Summarize cybersecurity incident findings."

    # Verify session.updated_at was updated to match message creation
    refreshed_session = chat_svc.get_session(session.id)
    assert refreshed_session.updated_at >= initial_updated_at

    time.sleep(0.01)

    # 3. Add assistant message with public execution summary
    asst_msg = chat_svc.add_assistant_message(
        session_id=session.id,
        content="Executive summary generated successfully.",
        execution_summary="Ingested 1 telemetry log, identified 3 indicators of compromise.",
    )
    assert asst_msg.role == MessageRole.ASSISTANT
    assert asst_msg.execution_summary is not None

    # Verify second updated_at touch
    second_refreshed = chat_svc.get_session(session.id)
    assert second_refreshed.updated_at >= refreshed_session.updated_at

    # 4. Chronological history
    history = chat_svc.get_history(session.id)
    assert len(history) == 2
    assert history[0].id == user_msg.id
    assert history[1].id == asst_msg.id

    # 5. Rename session
    renamed = chat_svc.rename_session(session.id, "Renamed Advisory Session")
    assert renamed.title == "Renamed Advisory Session"

    # 6. Delete session
    assert chat_svc.delete_session(session.id) is True
    with pytest.raises(EntityNotFoundError):
        chat_svc.get_session(session.id)


def test_chat_service_rejects_empty_content(service_env) -> None:
    """Verify ChatService rejects empty messages."""
    chat_svc: ChatService = service_env["chat_svc"]
    session = chat_svc.create_session(title="Empty Content Test")

    with pytest.raises(ValueError):
        chat_svc.add_user_message(session.id, content="   ")

    with pytest.raises(ValueError):
        chat_svc.add_assistant_message(session.id, content="")
