"""Deterministic EventDispatcher emitting ordered public execution events."""

from datetime import datetime, timezone
import logging
from typing import Any, Callable, Dict, List, Optional
import uuid
from pydantic import BaseModel, Field

from ..contracts import AgentEventType

logger = logging.getLogger("limo.agent.events")


class AgentPublicEvent(BaseModel):
    """Deterministic, frontend-safe execution event.
    
    MUST-FIX #4: Includes strictly increasing sequence counter alongside event_id and timestamps.
    STRICT ZERO PRIVATE CoT RULE: Never contains hidden chain-of-thought or raw internal reasoning.
    """
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:12]}")
    sequence: int = Field(description="Strictly monotonic sequence number for deterministic ordering")
    agent_id: str = Field(description="Correlating agent/session identifier")
    job_id: Optional[str] = Field(default=None, description="Correlating background transformation job ID")
    event_type: AgentEventType = Field(description="High-level lifecycle event type")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Safe summary payload")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class EventDispatcher:
    """Manages event sequence numbering and asynchronous distribution to frontend listeners."""

    def __init__(self):
        self._listeners: List[Callable[[AgentPublicEvent], Any]] = []
        # Monotonic counter per session/agent_id
        self._sequences: Dict[str, int] = {}

    def subscribe(self, listener: Callable[[AgentPublicEvent], Any]) -> None:
        """Register an async or sync event listener (e.g. SSE / WebSocket stream)."""
        self._listeners.append(listener)

    def unsubscribe(self, listener: Callable[[AgentPublicEvent], Any]) -> None:
        """Unregister an event listener."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _next_sequence(self, agent_id: str) -> int:
        """Get and increment monotonic sequence counter for an agent or session."""
        current = self._sequences.get(agent_id, 0) + 1
        self._sequences[agent_id] = current
        return current

    def get_current_sequence(self, agent_id: str) -> int:
        """Inspect current sequence counter without incrementing."""
        return self._sequences.get(agent_id, 0)

    async def emit(
        self,
        event_type: AgentEventType,
        agent_id: str,
        payload: Optional[Dict[str, Any]] = None,
        job_id: Optional[str] = None,
    ) -> AgentPublicEvent:
        """Construct, sequence, and dispatch a safe public agent event."""
        seq = self._next_sequence(agent_id)
        safe_payload = dict(payload or {})

        # Zero private CoT enforcement: Strip any accidentally included reasoning keys
        for forbidden in ("thought", "reasoning", "chain_of_thought", "private_scratchpad"):
            if forbidden in safe_payload:
                del safe_payload[forbidden]

        event = AgentPublicEvent(
            sequence=seq,
            agent_id=agent_id,
            job_id=job_id,
            event_type=event_type,
            payload=safe_payload,
        )

        logger.debug(
            "Emitted event %s (seq: %d, type: %s, agent: %s)",
            event.event_id,
            event.sequence,
            event.event_type.value,
            event.agent_id,
        )

        for listener in self._listeners:
            try:
                import inspect
                if inspect.iscoroutinefunction(listener):
                    await listener(event)
                else:
                    listener(event)
            except Exception as e:
                logger.warning("Event listener threw exception: %s", str(e))

        return event
