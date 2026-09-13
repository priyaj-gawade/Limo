"""Test-only scripted reasoning engine.

STRICTLY FOR AUTOMATED TESTING:
This class is isolated in the testing package to prevent accidental usage in production.
Enables deterministic verification of turn limits, tool dispatches, observations, and error flows.
"""

from typing import Callable, List, Optional
from ..actions import AgentAction
from ..brain import ReasoningEngine
from ..context import AgentContext
from ..contracts import BaseTool


class MockScriptedReasoningEngine(ReasoningEngine):
    """Deterministic, scripted decision engine strictly for unit and integration testing."""

    def __init__(
        self,
        scripted_actions: Optional[List[AgentAction]] = None,
        dynamic_decider: Optional[Callable[[AgentContext, List[BaseTool]], AgentAction]] = None,
    ):
        self.scripted_actions = list(scripted_actions or [])
        self.dynamic_decider = dynamic_decider
        self.calls_count = 0

    async def decide(self, context: AgentContext, available_tools: List[BaseTool]) -> AgentAction:
        """Return the next pre-scripted action or invoke the dynamic test decider."""
        self.calls_count += 1

        if self.dynamic_decider:
            return self.dynamic_decider(context, available_tools)

        if self.scripted_actions:
            return self.scripted_actions.pop(0)

        # Default fallback if script exhausted
        return AgentAction.final_response("Test execution finished (default scripted fallback)")
