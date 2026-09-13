"""Action definitions and decisions emitted by the Limo Agent reasoning engine."""

from enum import StrEnum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ActionType(StrEnum):
    """Types of actions an agent decision turn can take."""
    FINAL_RESPONSE = "final_response"
    TOOL_CALL = "tool_call"
    DELEGATE = "delegate"
    ERROR = "error"


class ToolCallPayload(BaseModel):
    """Structure for a single requested tool invocation."""
    tool_name: str = Field(description="Name of the registered tool to execute")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Validated tool arguments")
    call_id: str = Field(description="Unique identifier for correlation with observations")


class AgentAction(BaseModel):
    """Decision output produced by the agent reasoning engine."""
    action_type: ActionType = Field(description="Target action to perform")
    tool_calls: List[ToolCallPayload] = Field(
        default_factory=list,
        description="List of tool calls to execute sequentially in this turn"
    )
    response_text: Optional[str] = Field(
        default=None,
        description="Public assistant response content when action_type is FINAL_RESPONSE"
    )
    artifact_ids: List[str] = Field(
        default_factory=list,
        description="List of deliverable artifact IDs referenced or delivered in this turn"
    )
    execution_summary: Optional[str] = Field(
        default=None,
        description="Safe, high-level summary of steps taken (strictly zero private chain-of-thought)"
    )
    subagent_name: Optional[str] = Field(
        default=None,
        description="Target specialist subagent name when action_type is DELEGATE"
    )
    error: Optional[str] = Field(
        default=None,
        description="Error details if action_type is ERROR"
    )

    @classmethod
    def delegate(cls, subagent_name: str, instructions: str) -> "AgentAction":
        """Factory for a subagent delegation action."""
        return cls(
            action_type=ActionType.DELEGATE,
            subagent_name=subagent_name,
            response_text=instructions,
        )

    @classmethod
    def final_response(
        cls,
        text: str,
        artifact_ids: Optional[List[str]] = None,
        summary: Optional[str] = None
    ) -> "AgentAction":
        """Factory for a terminal assistant response."""
        return cls(
            action_type=ActionType.FINAL_RESPONSE,
            response_text=text,
            artifact_ids=artifact_ids or [],
            execution_summary=summary,
        )

    @classmethod
    def tool_call(
        cls,
        tool_name: str,
        arguments: Dict[str, Any],
        call_id: str
    ) -> "AgentAction":
        """Factory for a single tool call action."""
        return cls(
            action_type=ActionType.TOOL_CALL,
            tool_calls=[ToolCallPayload(tool_name=tool_name, arguments=arguments, call_id=call_id)],
        )

    @classmethod
    def tool_calls_batch(cls, calls: List[ToolCallPayload]) -> "AgentAction":
        """Factory for sequential batch tool calls."""
        return cls(
            action_type=ActionType.TOOL_CALL,
            tool_calls=calls,
        )

    @classmethod
    def fail(cls, error_message: str) -> "AgentAction":
        """Factory for an unrecoverable failure action."""
        return cls(
            action_type=ActionType.ERROR,
            error=error_message,
        )
