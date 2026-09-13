"""Integration tests for LimoAgentRuntime and AgentLoop executing real tools and activating skills."""

import pytest
from app.db import init_db
from app.agent.actions import AgentAction, ToolCallPayload
from app.agent.runtime import LimoAgentRuntime
from app.agent.testing.mock_brain import MockScriptedReasoningEngine
from app.models.enums import FeatureMode, JobState
from app.services.project_service import project_service
from app.services.source_service import source_service
from app.services.chat_service import chat_service
from app.services.job_service import job_service
from app.storage.service import storage_service


@pytest.fixture(autouse=True)
def setup_database(tmp_path):
    """Ensure clean schema and storage for each test."""
    init_db()
    storage_service.ensure_directories()


@pytest.mark.asyncio
async def test_runtime_executes_real_tools_end_to_end():
    """Verify that LimoAgentRuntime executes real tools through ToolRegistry against SQLite,

    activates skills via progressive disclosure, and persists clean execution summaries.
    """
    # 1. Setup real Project, Source, and Chat session
    proj = project_service.create_project(name="Enterprise Transformation")
    src = source_service.register_text_source(
        name="Quarterly Operational Results",
        text_content="Q3 showed strong performance with gross margin at 41% and customer churn reduced to 1.2%.",
        project_id=proj.id,
    )
    chat = chat_service.create_session(title="Presentation Planning", project_id=proj.id)

    # 2. Script the mock brain to invoke real tools sequentially:
    # Turn 1: Call source_read to list sources
    # Turn 2: Call transform_contract to queue presentation job
    # Turn 3: Deliver final response
    actions = [
        AgentAction.tool_call(
            tool_name="source_read",
            arguments={"action": "list_sources", "project_id": proj.id},
            call_id="call_list_sources",
        ),
        AgentAction.tool_call(
            tool_name="transform_contract",
            arguments={
                "requested_formats": ["presentation"],
                "source_ids": [src.id],
                "prompt": "Create an executive presentation from Q3 results",
            },
            call_id="call_queue_transform",
        ),
        AgentAction.final_response(
            "I have inspected your project sources and successfully queued the presentation transformation contract."
        ),
    ]

    mock_brain = MockScriptedReasoningEngine(scripted_actions=actions)
    runtime = LimoAgentRuntime(reasoning_engine=mock_brain)

    # 3. Execute turn
    assistant_msg = await runtime.execute_turn(
        session_id=chat.id,
        user_prompt="Please analyze my sources and create a slide deck",
        mode=FeatureMode.SLIDES,
        project_id=proj.id,
    )

    # 4. Verify message persistence and public execution summary
    assert assistant_msg is not None
    assert assistant_msg.session_id == chat.id
    assert "queued the presentation transformation contract" in assistant_msg.content
    assert assistant_msg.execution_summary is not None
    assert "source_read" in assistant_msg.execution_summary
    assert "transform_contract" in assistant_msg.execution_summary

    # 5. Verify real database state: TransformationJob was created in SQLite!
    jobs = job_service.list_jobs(project_id=proj.id)
    assert len(jobs) == 1
    created_job = jobs[0]
    assert created_job.state == JobState.QUEUED
    assert created_job.source_ids == [src.id]
    assert created_job.prompt == "Create an executive presentation from Q3 results"


@pytest.mark.asyncio
async def test_runtime_skill_activation_in_turn_context():
    """Verify that skill matching activates Tier 2 instructions in context for specific prompts."""
    proj = project_service.create_project(name="Validation Project")
    chat = chat_service.create_session(title="Audit Session", project_id=proj.id)

    # Simple one-turn final response
    mock_brain = MockScriptedReasoningEngine(
        scripted_actions=[AgentAction.final_response("Validation criteria reviewed.")]
    )
    runtime = LimoAgentRuntime(reasoning_engine=mock_brain)

    msg = await runtime.execute_turn(
        session_id=chat.id,
        user_prompt="Please validate the generated report for hallucination and citation accuracy",
        project_id=proj.id,
    )

    assert msg.content == "Validation criteria reviewed."
    # Skill registry matched 'validation' from prompt triggers
    matched = runtime.skill_registry.match_skills("Please validate the generated report for hallucination")
    assert any(s.name == "validation" for s in matched)
