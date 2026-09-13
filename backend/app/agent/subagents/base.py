"""Base class and result contract for bounded specialist subagents."""

from abc import ABC, abstractmethod
import logging
import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from ..context import AgentContext, AgentLimits
from ..contracts import AgentState, BaseTool

logger = logging.getLogger("limo.agent.subagents.base")


class SubagentResult(BaseModel):
    """Outcome produced by a delegated specialist subagent."""
    subagent_name: str
    status: AgentState = AgentState.COMPLETED
    findings: str = Field(description="Synthesized summary or findings from the subagent")
    data: Dict[str, Any] = Field(default_factory=dict, description="Structured extracted data")
    turns_used: int = 0
    tool_calls_used: int = 0
    duration_sec: float = 0.0
    error: Optional[str] = None


class BaseSubagent(ABC):
    """Abstract specialist subagent with isolated context, scoped whitelist, and bounded limits."""

    name: str
    role: str
    description: str
    tool_whitelist: List[str]

    def __init__(self, limits: Optional[AgentLimits] = None):
        self.limits = limits or AgentLimits(
            max_turns=5,
            max_tool_calls=10,
            max_execution_time_sec=30.0,
            max_context_tokens=4096,
        )

    def get_scoped_tools(self, available_tools: List[BaseTool]) -> List[BaseTool]:
        """Filter tools strictly to this subagent's authorized whitelist."""
        allowed = set(self.tool_whitelist)
        return [t for t in available_tools if t.name in allowed]

    @abstractmethod
    async def run(
        self,
        task: str,
        context: AgentContext,
        available_tools: List[BaseTool],
    ) -> SubagentResult:
        """Execute specialist task within scoped tools and bounded limits."""
        pass
