"""Unit and integration tests for AgentContext, AgentContextManager, and targeted source retrieval."""

import pytest
from app.agent.context import (
    AgentContext,
    AgentContextManager,
    AgentLimits,
    SourceExcerpt,
)
from app.agent.contracts import ToolResult
from app.db.connection import get_connection
from app.models.enums import FeatureMode, MessageRole
from app.models.chat import Message
from app.services.chat_service import chat_service
from app.services.project_service import project_service
from app.services.source_service import source_service


def test_agent_limits_defaults():
    """Verify safety limit defaults."""
    limits = AgentLimits()
    assert limits.max_turns == 10
    assert limits.max_tool_calls == 20
    assert limits.max_execution_time_sec == 60.0
    assert limits.max_context_tokens == 16000


def test_token_estimation():
    """Verify token heuristic calculation."""
    manager = AgentContextManager()
    assert manager.estimate_tokens("") == 0
    assert manager.estimate_tokens("word") == 1
    assert manager.estimate_tokens("a" * 400) == 100


def test_observation_recording():
    """Verify recording observations in context scratchpad."""
    manager = AgentContextManager()
    context = AgentContext(session_id="chat_test_123")

    result = ToolResult.ok({"status": "healthy"}, metadata={"source": "probe"})
    obs = manager.record_observation(context, "health_tool", "call_001", result)

    assert obs.tool_name == "health_tool"
    assert obs.call_id == "call_001"
    assert context.total_tool_calls == 1
    assert len(context.observations) == 1
    assert context.observations[0].result.output == {"status": "healthy"}


def test_targeted_source_retrieval_filters_irrelevant_files():
    """Verify targeted source retrieval extracts only relevant sources matching prompt."""
    proj = project_service.create_project("Source Retrieval Test", "Testing targeted retrieval")
    manager = AgentContextManager()

    try:
        # 1. Register 3 sources with distinct content
        src_audit = source_service.register_text_source(
            project_id=proj.id,
            name="telemetry_audit.txt",
            text_content="National power grid telemetry audit report. High voltage feeder lines exhibit zero anomalies in Sector 4.",
        )
        src_finance = source_service.register_text_source(
            project_id=proj.id,
            name="financial_ledger.csv",
            text_content="Q3 quarterly accounting ledger. Revenue: $4.2M, operating expenses: $1.8M, capital investments: $500k.",
        )
        src_personnel = source_service.register_text_source(
            project_id=proj.id,
            name="staff_roster.txt",
            text_content="Field engineering personnel assignments and emergency on-call contact phone numbers for substation operators.",
        )

        # 2. Query targeted retrieval for 'grid telemetry anomalies'
        excerpts = manager.retrieve_relevant_sources(
            prompt="Investigate power grid telemetry anomalies across sectors",
            project_id=proj.id,
            max_sources=2,
            max_chars_per_source=1000,
        )

        assert len(excerpts) >= 1
        # The telemetry audit MUST be the top result
        top = excerpts[0]
        assert top.source_id == src_audit.id
        assert top.name == "telemetry_audit.txt"
        assert "feeder lines exhibit zero anomalies" in top.snippet
        assert top.relevance_score > 0

        # Unrelated financial and personnel files should NOT be the top hit
        source_names = [e.name for e in excerpts]
        assert "financial_ledger.csv" not in source_names or excerpts[0].source_id != src_finance.id

    finally:
        project_service.delete_project(proj.id)


def test_source_excerpt_budget_is_not_arbitrary():
    """Verify that source excerpts are budget-driven and not artificially capped at 300 chars."""
    proj = project_service.create_project("Budget Test Project", "Testing excerpt size")
    manager = AgentContextManager()

    long_text = "Data point " + " ".join(f"index_{i}: value_{i * 2}" for i in range(200))  # ~2,500 chars

    try:
        src = source_service.register_text_source(
            project_id=proj.id,
            name="sensor_data.txt",
            text_content=long_text,
        )

        # Ask for up to 1,500 chars
        excerpts = manager.retrieve_relevant_sources(
            prompt="Analyze sensor data values",
            project_id=proj.id,
            max_sources=1,
            max_chars_per_source=1500,
        )

        assert len(excerpts) == 1
        # Should contain significantly more than 300 characters
        assert len(excerpts[0].snippet) > 1000
        assert "Data point" in excerpts[0].snippet

    finally:
        project_service.delete_project(proj.id)


def test_context_hydration_from_sqlite():
    """Verify load_context loads messages, active mode, and metadata correctly."""
    proj = project_service.create_project("Hydration Test", "Testing load_context")
    session = chat_service.create_session("Hydration Session", project_id=proj.id, mode=FeatureMode.DOCS)

    chat_service.add_user_message(session.id, "Hello, can you synthesize the audit?")
    chat_service.add_assistant_message(session.id, "I can help with that.", mode=FeatureMode.DOCS)

    manager = AgentContextManager()

    try:
        context = manager.load_context(
            session_id=session.id,
            user_request="Please outline the deliverables",
            project_id=proj.id,
            limits=AgentLimits(max_turns=5),
        )

        assert context.session_id == session.id
        assert context.project_id == proj.id
        assert context.active_mode == FeatureMode.DOCS
        assert len(context.messages) == 2
        assert context.messages[0].role == MessageRole.USER
        assert context.messages[1].role == MessageRole.ASSISTANT
        assert context.limits.max_turns == 5

    finally:
        project_service.delete_project(proj.id)


def test_sliding_window_truncation():
    """Verify that prune_or_truncate keeps context within token limits while preserving bookends."""
    manager = AgentContextManager()
    limits = AgentLimits(max_context_tokens=100)  # ~400 characters budget

    # Create 10 messages of 100 chars each (~250 tokens total, exceeds 100 tokens budget)
    messages = [
        Message(session_id="chat_1", role=MessageRole.USER, content=f"Message {i}: " + "x" * 80)
        for i in range(10)
    ]

    context = AgentContext(
        session_id="chat_1",
        messages=messages,
        limits=limits,
    )

    pruned = manager.prune_or_truncate(context)

    # Must preserve the first message
    assert pruned.messages[0].content == messages[0].content
    # Must preserve the latest turns
    assert pruned.messages[-1].content == messages[-1].content
    # Must have fewer messages than the original 10
    assert len(pruned.messages) < len(messages)
