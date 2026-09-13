"""Unit tests for Phase D4.5: MCP Client Adapter and Namespaced Tool Wrappers."""

import pytest
from app.agent.contracts import PermissionType
from app.agent.mcp.adapters.genoffice_adapter import GenOfficeBoundaryContract
from app.agent.mcp.adapters.video_adapter import VideoEngineBoundaryContract
from app.agent.mcp.client import MCPClientAdapter, MCPTransportType


def test_mcp_transport_types():
    assert MCPTransportType.STDIO == "stdio"
    assert MCPTransportType.STREAMABLE_HTTP == "streamable_http"
    assert MCPTransportType.LEGACY_SSE == "legacy_sse"


@pytest.mark.asyncio
async def test_mcp_tool_namespacing_and_permissions():
    adapter = MCPClientAdapter()
    genoffice_tools = GenOfficeBoundaryContract.register(adapter)

    # MUST-FIX #2: External tools must be namespaced
    assert len(genoffice_tools) == 3
    tool_names = [t.name for t in genoffice_tools]
    assert "mcp.genoffice.create_document" in tool_names
    assert "mcp.genoffice.create_presentation" in tool_names
    assert "mcp.genoffice.create_spreadsheet" in tool_names

    # Check permission type
    for tool in genoffice_tools:
        assert tool.permission_type == PermissionType.EXTERNAL_DISPATCH

    # Video contract
    video_tools = VideoEngineBoundaryContract.register(adapter)
    assert len(video_tools) == 1
    assert video_tools[0].name == "mcp.openmontage.render_video"
    assert video_tools[0].permission_type == PermissionType.EXTERNAL_DISPATCH


@pytest.mark.asyncio
async def test_mcp_execution_success():
    adapter = MCPClientAdapter()
    genoffice_tools = GenOfficeBoundaryContract.register(adapter)
    doc_tool = next(t for t in genoffice_tools if t.name == "mcp.genoffice.create_document")

    res = await doc_tool.execute({"title": "Quarterly Report", "content_markdown": "# Title\nBody"})
    assert res.success is True
    assert res.metadata["server"] == "genoffice"
    assert res.metadata["tool"] == "create_document"


@pytest.mark.asyncio
async def test_mcp_error_containment():
    adapter = MCPClientAdapter()
    genoffice_tools = GenOfficeBoundaryContract.register(adapter)
    doc_tool = next(t for t in genoffice_tools if t.name == "mcp.genoffice.create_document")

    # Simulate disconnection
    adapter.disconnect_server("genoffice")
    res = await doc_tool.execute({"title": "Test", "content_markdown": "Test"})

    # Error containment: fails gracefully without unhandled exception
    assert res.success is False
    assert "not connected" in res.error
