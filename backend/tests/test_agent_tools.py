"""Unit and integration tests for Limo Agent Tools and ToolRegistry."""

import pytest
from app.db import init_db
from app.agent.tools import (
    ToolRegistry,
    SourceReadTool,
    SourceRegisterTool,
    ProjectTool,
    ChatTool,
    TransformContractTool,
    JobTool,
    ArtifactTool,
    StorageTool,
    create_default_tool_registry,
)
from app.agent.contracts import BaseTool, ToolResult, PermissionType
from app.agent.context import AgentContext
from app.services.project_service import project_service
from app.services.source_service import source_service
from app.services.chat_service import chat_service
from app.services.artifact_service import artifact_service
from app.storage.service import storage_service
from app.models.enums import ArtifactType, OutputFormat, JobState


@pytest.fixture(autouse=True)
def setup_database(tmp_path):
    """Ensure clean schema and storage for each test."""
    init_db()
    storage_service.ensure_directories()


@pytest.mark.asyncio
async def test_tool_registry_registration_and_schemas():
    """Verify tool registration, naming validation, duplicate rejection, and schema generation."""
    registry = ToolRegistry()
    tool = ProjectTool()
    registry.register(tool)

    assert registry.get("project_tool") == tool
    assert len(registry.list_tools()) == 1

    # Duplicate rejection
    with pytest.raises(ValueError, match="already registered"):
        registry.register(tool)

    # Invalid name format rejection
    class BadNameTool(BaseTool):
        name = "Bad-Name!"
        description = "Invalid"
        permission_type = PermissionType.READ
        @property
        def parameters_schema(self):
            return {}
        async def execute(self, args, context=None):
            return ToolResult.ok(None)

    with pytest.raises(ValueError, match="must be snake_case"):
        registry.register(BadNameTool())

    # Schema generation
    schemas = registry.get_schemas()
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "project_tool"
    assert "parameters" in schemas[0]["function"]


@pytest.mark.asyncio
async def test_default_tool_registry_factory():
    """Verify default factory initializes all 8 core tools."""
    registry = create_default_tool_registry()
    tools = registry.list_tools()
    assert len(tools) == 8

    expected_names = {
        "source_read", "source_register", "project_tool", "chat_tool",
        "transform_contract", "job_tool", "artifact_tool", "storage_tool",
    }
    assert {t.name for t in tools} == expected_names


@pytest.mark.asyncio
async def test_project_tool_lifecycle():
    """Test project_tool against real ProjectService."""
    tool = ProjectTool()

    # 1. Create project
    create_res = await tool.execute({"action": "create_project", "name": "Agent Project Alpha", "description": "Test"})
    assert create_res.success is True
    proj_id = create_res.output["id"]
    assert proj_id.startswith("proj_")

    # 2. Get project
    get_res = await tool.execute({"action": "get_project", "project_id": proj_id})
    assert get_res.success is True
    assert get_res.output["name"] == "Agent Project Alpha"

    # 3. List projects
    list_res = await tool.execute({"action": "list_projects"})
    assert list_res.success is True
    assert list_res.output["count"] >= 1


@pytest.mark.asyncio
async def test_source_read_and_register_tools():
    """Test source_read and source_register tools with permission distinction."""
    proj = project_service.create_project("Source Test Project")
    context = AgentContext(session_id="dummy_sess", project_id=proj.id)

    read_tool = SourceReadTool()
    register_tool = SourceRegisterTool()

    assert read_tool.permission_type == PermissionType.READ
    assert register_tool.permission_type == PermissionType.WRITE

    # 1. Register a text source using WRITE tool
    reg_res = await register_tool.execute({
        "name": "Earnings Q3",
        "text_content": "Total gross margins exceeded 42.5 percent across all business units.",
    }, context=context)
    assert reg_res.success is True
    src_id = reg_res.output["source_id"]

    # 2. List sources using READ tool
    list_res = await read_tool.execute({"action": "list_sources"}, context=context)
    assert list_res.success is True
    assert list_res.output["count"] == 1
    assert list_res.output["sources"][0]["id"] == src_id

    # 3. Read content with character budget
    read_res = await read_tool.execute({
        "action": "get_source_content",
        "source_id": src_id,
        "max_chars": 20,
    }, context=context)
    assert read_res.success is True
    assert read_res.output["truncated"] is True
    assert len(read_res.output["content"]) == 20


@pytest.mark.asyncio
async def test_transform_contract_tool_queues_job_without_fake_generation():
    """Verify TransformContractTool creates real TransformationJob contract and does not fake deliverables."""
    proj = project_service.create_project("Transform Contract Project")
    src = source_service.register_text_source("Market Report", "Inflation data and market trends.", project_id=proj.id)
    chat = chat_service.create_session("Transform Session", project_id=proj.id)
    context = AgentContext(session_id=chat.id, project_id=proj.id)

    tool = TransformContractTool()
    assert tool.permission_type == PermissionType.TRANSFORM

    result = await tool.execute({
        "requested_formats": ["presentation", "document"],
        "source_ids": [src.id],
        "prompt": "Create an executive summary and slides",
    }, context=context)

    assert result.success is True
    job_id = result.output["job_id"]
    assert result.output["queued"] is True
    assert "presentation" in result.output["requested_formats"]
    assert "document" in result.output["requested_formats"]

    # Verify real state in SQLite
    from app.services.job_service import job_service
    stored_job = job_service.get_job(job_id)
    assert stored_job.state == JobState.QUEUED
    assert stored_job.prompt == "Create an executive summary and slides"
    assert stored_job.source_ids == [src.id]


@pytest.mark.asyncio
async def test_storage_tool_strict_authorization_guard():
    """MUST-FIX #2: Verify storage_reader enforces strict project authorization."""
    # Create two separate projects
    proj_a = project_service.create_project("Project Alpha")
    proj_b = project_service.create_project("Project Beta")

    # Create real file in storage and register artifact under Project A
    storage_ref, size, content_hash = storage_service.save_artifact_file(
        artifact_id="art_auth_test",
        filename="brief.txt",
        content="Confidential corporate roadmap for Project Alpha.".encode("utf-8"),
    )
    art_a = artifact_service.register_artifact(
        title="Project Alpha Brief",
        artifact_type=ArtifactType.DOC,
        file_format=".txt",
        storage_ref=storage_ref,
        project_id=proj_a.id,
    )

    tool = StorageTool()

    # Case 1: Caller in Project A context -> Authorized
    context_a = AgentContext(session_id="sess_a", project_id=proj_a.id)
    auth_res = await tool.execute({"artifact_id": art_a.id}, context=context_a)
    assert auth_res.success is True
    assert "Confidential corporate roadmap" in auth_res.output["content_preview"]

    # Case 2: Caller in Project B context -> Access Denied!
    context_b = AgentContext(session_id="sess_b", project_id=proj_b.id)
    denied_res = await tool.execute({"artifact_id": art_a.id}, context=context_b)
    assert denied_res.success is False
    assert "Access denied" in denied_res.error
    assert proj_b.id in denied_res.error


@pytest.mark.asyncio
async def test_chat_and_job_and_artifact_tools():
    """Verify chat_manager, job_manager, and artifact_manager tools."""
    proj = project_service.create_project("Composite Tool Project")
    chat = chat_service.create_session("Chat Tool Test", project_id=proj.id)
    context = AgentContext(session_id=chat.id, project_id=proj.id)

    # 1. ChatTool: add user message and read history
    chat_service.add_user_message(chat.id, "Hello Limo agent!")
    chat_tool = ChatTool()
    history_res = await chat_tool.execute({"action": "get_history"}, context=context)
    assert history_res.success is True
    assert history_res.output["count"] == 1
    assert history_res.output["messages"][0]["content"] == "Hello Limo agent!"

    # 2. Transform + JobTool: query job status
    transform_tool = TransformContractTool()
    t_res = await transform_tool.execute({
        "requested_formats": ["summary"],
        "prompt": "Summarize findings",
    }, context=context)
    job_id = t_res.output["job_id"]

    job_tool = JobTool()
    job_res = await job_tool.execute({"action": "get_job", "job_id": job_id})
    assert job_res.success is True
    assert job_res.output["state"] == "queued"


@pytest.mark.asyncio
async def test_tool_registry_safe_error_containment():
    """Verify ToolRegistry.execute handles validation errors and missing tools without raising."""
    registry = create_default_tool_registry()

    # Tool not found
    res = await registry.execute("non_existent_tool", {})
    assert res.success is False
    assert res.metadata["error_code"] == "TOOL_NOT_FOUND"

    # Validation error inside tool
    res2 = await registry.execute("source_read", {"action": "list_sources"})  # missing project_id
    assert res2.success is False
    assert "Missing required 'project_id'" in res2.error
