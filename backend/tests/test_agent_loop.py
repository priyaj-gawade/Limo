"""Unit and integration tests for AgentLoop, safety limits, sequential tools, and LimoAgentRuntime."""

import asyncio
import pytest
from typing import Any, Dict

from app.agent.actions import ActionType, AgentAction, ToolCallPayload
from app.agent.context import AgentContext, AgentLimits
from app.agent.contracts import AgentState, BaseTool, PermissionType, ToolResult
from app.agent.loop import AgentLoop
from app.agent.runtime import LimoAgentRuntime
from app.agent.testing.mock_brain import MockScriptedReasoningEngine
from app.models.enums import FeatureMode, MessageRole
from app.services.chat_service import chat_service
from app.services.project_service import project_service


class DummyEchoTool(BaseTool):
    """Simple test tool that appends a suffix to input message."""
    name = "echo_tool"
    description = "Test tool for echoing input text"
    permission_type = PermissionType.READ

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        }

    async def execute(self, args: Dict[str, Any], context: Any = None) -> ToolResult:
        text = args.get("text", "")
        return ToolResult.ok(f"Echoed: {text}")


class FailingTool(BaseTool):
    """Test tool that explicitly throws an error."""
    name = "failing_tool"
    description = "Always fails"
    permission_type = PermissionType.READ

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, args: Dict[str, Any], context: Any = None) -> ToolResult:
        raise RuntimeError("Simulated internal tool crash")


@pytest.mark.asyncio
async def test_single_turn_final_response():
    """Verify single turn without tools completes cleanly."""
    engine = MockScriptedReasoningEngine(scripted_actions=[
        AgentAction.final_response("Here is the executive summary.", summary="Answered directly without tools.")
    ])
    loop = AgentLoop(reasoning_engine=engine)
    context = AgentContext(session_id="chat_test_single")

    result = await loop.run(context=context, available_tools=[DummyEchoTool()])

    assert result.status == AgentState.COMPLETED
    assert result.response_text == "Here is the executive summary."
    assert result.execution_summary == "Answered directly without tools."
    assert result.turns_used == 1
    assert result.tool_calls_used == 0


@pytest.mark.asyncio
async def test_multi_turn_sequential_tool_execution():
    """Verify multi-turn tool execution executes sequentially and records observations."""
    engine = MockScriptedReasoningEngine(scripted_actions=[
        # Turn 1: Call echo_tool twice in sequential batch
        AgentAction.tool_calls_batch([
            ToolCallPayload(tool_name="echo_tool", arguments={"text": "First"}, call_id="c1"),
            ToolCallPayload(tool_name="echo_tool", arguments={"text": "Second"}, call_id="c2"),
        ]),
        # Turn 2: Final response after observing both
        AgentAction.final_response("Both echoes processed successfully.")
    ])

    loop = AgentLoop(reasoning_engine=engine)
    context = AgentContext(session_id="chat_test_seq")

    result = await loop.run(context=context, available_tools=[DummyEchoTool()])

    assert result.status == AgentState.COMPLETED
    assert result.turns_used == 2
    assert result.tool_calls_used == 2
    assert len(context.observations) == 2
    assert context.observations[0].result.output == "Echoed: First"
    assert context.observations[1].result.output == "Echoed: Second"
    assert "Executed 2 tool operations" in result.execution_summary


@pytest.mark.asyncio
async def test_max_turns_safety_limit_enforced():
    """Verify loop terminates when max_turns is exceeded."""
    # Scripted engine that always requests another tool call and never finishes
    def infinite_loop_decider(ctx, tools):
        return AgentAction.tool_call("echo_tool", {"text": f"turn_{ctx.current_turn}"}, f"call_{ctx.current_turn}")

    engine = MockScriptedReasoningEngine(dynamic_decider=infinite_loop_decider)
    loop = AgentLoop(reasoning_engine=engine)
    context = AgentContext(
        session_id="chat_infinite",
        limits=AgentLimits(max_turns=3),
    )

    result = await loop.run(context=context, available_tools=[DummyEchoTool()])

    assert result.status == AgentState.FAILED
    assert "Maximum reasoning turns (3) exceeded" in result.error
    assert result.turns_used >= 3


@pytest.mark.asyncio
async def test_max_tool_calls_safety_limit_enforced():
    """Verify loop terminates when max_tool_calls is exceeded."""
    engine = MockScriptedReasoningEngine(scripted_actions=[
        AgentAction.tool_calls_batch([
            ToolCallPayload(tool_name="echo_tool", arguments={"text": "1"}, call_id="c1"),
            ToolCallPayload(tool_name="echo_tool", arguments={"text": "2"}, call_id="c2"),
            ToolCallPayload(tool_name="echo_tool", arguments={"text": "3"}, call_id="c3"),
        ])
    ])
    loop = AgentLoop(reasoning_engine=engine)
    context = AgentContext(
        session_id="chat_tool_limit",
        limits=AgentLimits(max_tool_calls=2),  # Limit is 2, action asks for 3
    )

    result = await loop.run(context=context, available_tools=[DummyEchoTool()])

    assert result.status == AgentState.FAILED
    assert "Tool call limit reached" in result.error or "Maximum tool calls" in result.error
    assert context.total_tool_calls >= 2


@pytest.mark.asyncio
async def test_execution_timeout_safety_limit_enforced():
    """Verify loop terminates when wall-clock execution time limit is breached."""
    class SlowTool(BaseTool):
        name = "slow_tool"
        description = "Simulates delay"
        permission_type = PermissionType.READ

        @property
        def parameters_schema(self) -> Dict[str, Any]:
            return {"type": "object", "properties": {}}

        async def execute(self, args: Dict[str, Any], context: Any = None) -> ToolResult:
            await asyncio.sleep(0.08)  # Exceeds 0.05s timeout
            return ToolResult.ok("Done")

    engine = MockScriptedReasoningEngine(scripted_actions=[
        AgentAction.tool_call("slow_tool", {}, "slow_1"),
        AgentAction.final_response("Should not be reached"),
    ])

    loop = AgentLoop(reasoning_engine=engine)
    context = AgentContext(
        session_id="chat_timeout",
        limits=AgentLimits(max_execution_time_sec=0.05),  # 50ms limit
    )

    result = await loop.run(context=context, available_tools=[SlowTool()])

    assert result.status == AgentState.FAILED
    assert "timed out" in result.error.lower()


@pytest.mark.asyncio
async def test_delegate_action_dispatched_in_d44():
    """Verify ActionType.DELEGATE is handled and dispatched to specialist subagents in D4.4."""
    engine = MockScriptedReasoningEngine(scripted_actions=[
        AgentAction.delegate(subagent_name="research_agent", instructions="Gather evidence"),
        AgentAction.final_response("Research completed."),
    ])
    loop = AgentLoop(reasoning_engine=engine)
    context = AgentContext(session_id="chat_delegate_d44")

    result = await loop.run(context=context, available_tools=[])

    assert result.status == AgentState.COMPLETED
    assert result.turns_used == 2
    assert "Research completed." in result.response_text


@pytest.mark.asyncio
async def test_tool_failure_is_captured_in_observation():
    """Verify that tool runtime exceptions are cleanly captured as failed ToolResults."""
    engine = MockScriptedReasoningEngine(scripted_actions=[
        AgentAction.tool_call("failing_tool", {}, "fail_1"),
        AgentAction.final_response("Recovered from tool error.")
    ])
    loop = AgentLoop(reasoning_engine=engine)
    context = AgentContext(session_id="chat_tool_fail")

    result = await loop.run(context=context, available_tools=[FailingTool()])

    assert result.status == AgentState.COMPLETED
    assert len(context.observations) == 1
    assert context.observations[0].result.success is False
    assert "Simulated internal tool crash" in context.observations[0].result.error


@pytest.mark.asyncio
async def test_limo_agent_runtime_full_turn_persists_to_sqlite():
    """Verify LimoAgentRuntime coordinates turn execution and persists assistant turn to SQLite."""
    proj = project_service.create_project("Runtime Test Project", "Testing LimoAgentRuntime")
    session = chat_service.create_session("Runtime Chat Session", project_id=proj.id, mode=FeatureMode.SLIDES)

    try:
        engine = MockScriptedReasoningEngine(scripted_actions=[
            AgentAction.tool_call("echo_tool", {"text": "Presentation Outline"}, "c1"),
            AgentAction.final_response(
                text="Here is your requested slide outline.",
                summary="Outlined slide sequence using echo tool.",
            )
        ])

        runtime = LimoAgentRuntime(reasoning_engine=engine)

        assistant_msg = await runtime.execute_turn(
            session_id=session.id,
            user_prompt="Please generate slide deck outline",
            mode=FeatureMode.SLIDES,
            project_id=proj.id,
            tools=[DummyEchoTool()],
        )

        assert assistant_msg.role == MessageRole.ASSISTANT
        assert assistant_msg.content == "Here is your requested slide outline."
        assert assistant_msg.mode == FeatureMode.SLIDES
        assert assistant_msg.execution_summary == "Outlined slide sequence using echo tool."

        # Verify chat history in SQLite has both user and assistant turns
        history = chat_service.get_history(session.id)
        assert len(history) == 2
        assert history[0].role == MessageRole.USER
        assert history[0].content == "Please generate slide deck outline"
        assert history[1].role == MessageRole.ASSISTANT
        assert history[1].content == "Here is your requested slide outline."

    finally:
        project_service.delete_project(proj.id)
