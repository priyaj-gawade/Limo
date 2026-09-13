"""Unit tests for Phase D4.6: EventDispatcher deterministic sequencing and zero CoT leakage."""

import pytest
from app.agent.contracts import AgentEventType
from app.agent.events.dispatcher import AgentPublicEvent, EventDispatcher


@pytest.mark.asyncio
async def test_event_deterministic_sequence_ordering():
    """MUST-FIX #4: Events must have strictly monotonic integer sequence numbers."""
    dispatcher = EventDispatcher()
    received_events = []

    def listener(evt: AgentPublicEvent):
        received_events.append(evt)

    dispatcher.subscribe(listener)

    # Emit three events for agent session "sess_alpha"
    e1 = await dispatcher.emit(AgentEventType.AGENT_STARTED, agent_id="sess_alpha", payload={"turn": 1})
    e2 = await dispatcher.emit(AgentEventType.TOOL_STARTED, agent_id="sess_alpha", payload={"tool": "source_read"})
    e3 = await dispatcher.emit(AgentEventType.TOOL_COMPLETED, agent_id="sess_alpha", payload={"tool": "source_read"})

    assert e1.sequence == 1
    assert e2.sequence == 2
    assert e3.sequence == 3
    assert len(received_events) == 3
    assert [e.sequence for e in received_events] == [1, 2, 3]

    # Another session starts at 1
    e_other = await dispatcher.emit(AgentEventType.AGENT_STARTED, agent_id="sess_beta")
    assert e_other.sequence == 1


@pytest.mark.asyncio
async def test_zero_cot_leakage_rule():
    """Verify private reasoning, thoughts, and scratchpads are stripped from public payloads."""
    dispatcher = EventDispatcher()
    event = await dispatcher.emit(
        AgentEventType.AGENT_THINKING,
        agent_id="sess_test",
        payload={
            "step": "Planning search",
            "thought": "Let me secretly inspect private table",
            "reasoning": "Internal CoT token stream",
            "progress_percent": 25,
        },
    )

    assert "step" in event.payload
    assert "progress_percent" in event.payload
    assert "thought" not in event.payload
    assert "reasoning" not in event.payload
