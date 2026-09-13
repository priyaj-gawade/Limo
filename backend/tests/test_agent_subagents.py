"""Unit tests for Phase D4.4: Specialist subagents and SubagentCoordinator."""

import pytest
from app.agent.actions import ActionType, AgentAction
from app.agent.context import AgentContext, AgentLimits
from app.agent.contracts import AgentState
from app.agent.loop import AgentLoop
from app.agent.subagents.analysis_agent import ContentAnalysisAgent
from app.agent.subagents.coordinator import SubagentCoordinator
from app.agent.subagents.research_agent import ResearchAgent
from app.agent.subagents.validation_agent import ValidationAgent
from app.agent.testing.mock_brain import MockScriptedReasoningEngine
from app.agent.tools.source_tool import SourceReadTool
from app.agent.tools.project_tool import ProjectTool


@pytest.mark.asyncio
async def test_subagent_tool_whitelist_scoping():
    researcher = ResearchAgent()
    assert set(researcher.tool_whitelist) == {"source_read", "project_tool", "chat_tool"}

    analysis = ContentAnalysisAgent()
    assert analysis.tool_whitelist == ["source_read"]

    validation = ValidationAgent()
    assert set(validation.tool_whitelist) == {"artifact_tool", "storage_tool", "source_read"}

    all_tools = [SourceReadTool(), ProjectTool()]
    scoped = analysis.get_scoped_tools(all_tools)
    assert len(scoped) == 1
    assert scoped[0].name == "source_read"


@pytest.mark.asyncio
async def test_coordinator_dispatch():
    coord = SubagentCoordinator()
    assert len(coord.list_subagents()) == 3

    ctx = AgentContext(session_id="sess_sub_1", user_request="Research climate patterns")
    result = await coord.dispatch("research_agent", "Summarize findings", ctx, [SourceReadTool()])

    assert result.status == AgentState.COMPLETED
    assert result.subagent_name == "research_agent"
    assert "Research synthesis" in result.findings


@pytest.mark.asyncio
async def test_agent_loop_subagent_delegation():
    coord = SubagentCoordinator()
    # Step 1: delegate to research_agent, Step 2: final response
    engine = MockScriptedReasoningEngine([
        AgentAction.delegate(subagent_name="research_agent", instructions="Find relevant files"),
        AgentAction.final_response("Here is the research: done."),
    ])
    loop = AgentLoop(reasoning_engine=engine, subagent_coordinator=coord)
    ctx = AgentContext(session_id="sess_loop_sub", user_request="Help me research")

    res = await loop.run(ctx, [SourceReadTool(), ProjectTool()])
    assert res.status == AgentState.COMPLETED
    assert res.turns_used == 2
    assert "Here is the research: done." in res.response_text
    # Scratchpad should record delegation observation
    assert len(ctx.observations) == 1
    assert "delegate:research_agent" in ctx.observations[0].tool_name
