"""Unit tests for Phase D4.1: Agent Infrastructure Foundational Contracts."""

import pytest
from app.agent.contracts import (
    AgentEventType,
    AgentState,
    BaseHook,
    BaseTool,
    HookEvent,
    PermissionType,
    ToolResult,
)


def test_tool_result_ok_and_fail():
    """Verify ToolResult factory helpers and serialization."""
    res_ok = ToolResult.ok({"artifact_id": "art_123"}, metadata={"duration_ms": 12.5})
    assert res_ok.success is True
    assert res_ok.output == {"artifact_id": "art_123"}
    assert res_ok.error is None
    assert res_ok.metadata["duration_ms"] == 12.5

    res_fail = ToolResult.fail("Source file not found", metadata={"source_id": "src_999"})
    assert res_fail.success is False
    assert res_fail.output is None
    assert res_fail.error == "Source file not found"
    assert res_fail.metadata["source_id"] == "src_999"

    # Serialization roundtrip
    dumped = res_ok.model_dump()
    loaded = ToolResult(**dumped)
    assert loaded.success == res_ok.success
    assert loaded.output == res_ok.output


def test_permission_types():
    """Verify permission enums cover security requirements."""
    expected = {"read", "write", "execute", "transform", "external_dispatch"}
    actual = {p.value for p in PermissionType}
    assert expected.issubset(actual)


def test_hook_events():
    """Verify lifecycle hook events."""
    expected = {
        "pre_tool_use",
        "post_tool_use",
        "pre_artifact_creation",
        "post_artifact_creation",
        "agent_start",
        "agent_stop",
        "agent_error",
    }
    actual = {h.value for h in HookEvent}
    assert expected.issubset(actual)


def test_public_agent_event_types():
    """Verify safe public event types (no private chain-of-thought)."""
    events = [e.value for e in AgentEventType]
    assert "agent.started" in events
    assert "tool.started" in events
    assert "tool.completed" in events
    assert "subagent.started" in events
    assert "artifact.created" in events
    # Ensure no chain of thought leaking event exists
    for ev in events:
        assert "chain_of_thought" not in ev
        assert "private" not in ev


@pytest.mark.asyncio
async def test_concrete_tool_implementation():
    """Verify defining and executing a concrete BaseTool subclass."""
    class EchoTool(BaseTool):
        name = "echo_tool"
        description = "Test tool that echoes input"
        permission_type = PermissionType.READ

        @property
        def parameters_schema(self):
            return {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            }

        async def execute(self, args, context=None):
            msg = args.get("message", "")
            return ToolResult.ok(f"Echo: {msg}")

    tool = EchoTool()
    assert tool.name == "echo_tool"
    assert tool.permission_type == PermissionType.READ
    assert "message" in tool.parameters_schema["properties"]

    result = await tool.execute({"message": "Hello Limo Agent"})
    assert result.success is True
    assert result.output == "Echo: Hello Limo Agent"
