"""Coordinator dispatching tasks to registered specialist subagents."""

import logging
from typing import Dict, List, Optional

from ..context import AgentContext
from ..contracts import AgentState, BaseTool
from .analysis_agent import ContentAnalysisAgent
from .base import BaseSubagent, SubagentResult
from .research_agent import ResearchAgent
from .validation_agent import ValidationAgent

logger = logging.getLogger("limo.agent.subagents.coordinator")


class SubagentCoordinator:
    """Central registry and dispatch coordinator for specialist worker subagents."""

    def __init__(self, subagents: Optional[List[BaseSubagent]] = None):
        self._subagents: Dict[str, BaseSubagent] = {}
        if subagents:
            for s in subagents:
                self.register(s)
        else:
            # Register default specialists
            self.register(ResearchAgent())
            self.register(ContentAnalysisAgent())
            self.register(ValidationAgent())

    def register(self, subagent: BaseSubagent) -> None:
        """Register a specialist subagent instance."""
        self._subagents[subagent.name] = subagent
        logger.debug("Registered subagent: %s (%s)", subagent.name, subagent.role)

    def get_subagent(self, name: str) -> Optional[BaseSubagent]:
        """Retrieve subagent by unique name."""
        return self._subagents.get(name)

    def list_subagents(self) -> List[BaseSubagent]:
        """List all registered specialist subagents."""
        return list(self._subagents.values())

    async def dispatch(
        self,
        subagent_name: str,
        task: str,
        context: AgentContext,
        available_tools: List[BaseTool],
    ) -> SubagentResult:
        """Dispatch a delegated task to the named specialist subagent."""
        subagent = self.get_subagent(subagent_name)
        if not subagent:
            err = f"Unknown subagent '{subagent_name}'. Available: {list(self._subagents.keys())}"
            logger.error(err)
            return SubagentResult(
                subagent_name=subagent_name,
                status=AgentState.FAILED,
                findings="",
                error=err,
            )

        logger.info("Dispatching task to subagent '%s': %s", subagent_name, task)
        return await subagent.run(task, context, available_tools)
