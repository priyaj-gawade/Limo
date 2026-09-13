"""Core contracts, protocols, and data models for Limo Agent Infrastructure.

Defines the fundamental interfaces for:
- Tools and ToolResults
- Permission definitions
- Lifecycle Hook events
- Agent public execution events
- Subagent boundaries
"""

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PermissionType(StrEnum):
    """Categorized capability permissions for security enforcement."""
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    TRANSFORM = "transform"
    EXTERNAL_DISPATCH = "external_dispatch"


class HookEvent(StrEnum):
    """Agent lifecycle interception points."""
    PRE_TOOL_USE = "pre_tool_use"
    POST_TOOL_USE = "post_tool_use"
    PRE_ARTIFACT_CREATION = "pre_artifact_creation"
    POST_ARTIFACT_CREATION = "post_artifact_creation"
    AGENT_START = "agent_start"
    AGENT_STOP = "agent_stop"
    AGENT_ERROR = "agent_error"


class AgentEventType(StrEnum):
    """Safe, public execution events emitted during agent operations.
    
    Exposes only high-level status and summaries. Never exposes private chain-of-thought.
    """
    AGENT_STARTED = "agent.started"
    AGENT_THINKING = "agent.thinking"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    SUBAGENT_STARTED = "subagent.started"
    SUBAGENT_COMPLETED = "subagent.completed"
    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    ARTIFACT_CREATED = "artifact.created"
    AGENT_FAILED = "agent.failed"
    AGENT_COMPLETED = "agent.completed"


class AgentState(StrEnum):
    """Execution status of the primary agent loop."""
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING_TOOL = "executing_tool"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"


class ToolResult(BaseModel):
    """Structured result returned by every tool execution."""
    success: bool = Field(description="Whether the tool operation completed successfully")
    output: Any = Field(default=None, description="Structured result data, entity, or human-readable text")
    error: Optional[str] = Field(default=None, description="Explicit error message if tool failed")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Diagnostics, execution timing, or stats")

    @classmethod
    def ok(cls, output: Any, metadata: Optional[Dict[str, Any]] = None) -> "ToolResult":
        """Create a successful tool execution result."""
        return cls(success=True, output=output, metadata=metadata or {})

    @classmethod
    def fail(cls, error: str, metadata: Optional[Dict[str, Any]] = None) -> "ToolResult":
        """Create a failed tool execution result."""
        return cls(success=False, error=error, metadata=metadata or {})


class BaseTool(ABC):
    """Abstract base class for all Limo Agent tools.
    
    Tools wrap real Limo business services (Phase D3) instead of accessing persistence directly.
    """

    name: str
    description: str
    permission_type: PermissionType = PermissionType.READ

    @property
    @abstractmethod
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema dictionary describing the tool arguments."""
        pass

    @abstractmethod
    async def execute(self, args: Dict[str, Any], context: Optional[Any] = None) -> ToolResult:
        """Execute the tool operation against real Limo services and return a ToolResult."""
        pass


class BaseHook(ABC):
    """Abstract base class for agent lifecycle interceptors."""

    event: HookEvent

    @abstractmethod
    async def execute(self, payload: Dict[str, Any], context: Optional[Any] = None) -> Dict[str, Any]:
        """Process lifecycle event payload. May mutate payload or raise exception to block execution."""
        pass
