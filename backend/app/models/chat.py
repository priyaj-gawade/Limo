"""ChatSession and Message domain models."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import Field, field_validator, model_validator
from .artifact import Artifact
from .base import LimoBaseModel
from .enums import FeatureMode, MessageRole
from ..core.ids import generate_chat_id, generate_message_id


class MessageAttachment(LimoBaseModel):
    """File attachment linked to a chat message turn."""
    id: str = Field(description="Unique attachment identifier")
    name: str = Field(description="Attachment filename")
    size_bytes: int = Field(ge=0, description="Attachment size in bytes")
    mime_type: str = Field(description="MIME type")
    source_id: Optional[str] = Field(default=None, description="Linked ingested source ID if registered")


class Message(LimoBaseModel):
    """Single conversational turn in a Limo chat session."""

    id: str = Field(default_factory=generate_message_id, description="Stable message ID with 'msg_' prefix")
    session_id: str = Field(description="Associated ChatSession ID")
    role: MessageRole = Field(description="Identity of the message author")
    content: str = Field(description="Public conversational message text")
    mode: Optional[FeatureMode] = Field(default=None, description="Active creation mode during turn submission")
    attachments: List[MessageAttachment] = Field(default_factory=list, description="User-supplied attachments")
    artifact_ids: List[str] = Field(default_factory=list, description="Referenced generated deliverable artifact IDs")
    artifacts: List[Artifact] = Field(default_factory=list, description="Resolved deliverable artifact objects")
    execution_summary: Optional[str] = Field(
        default=None,
        description="Public safe execution summary (strictly public metrics/progress, NEVER private chain-of-thought)"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC turn creation timestamp"
    )

    @field_validator("id")
    @classmethod
    def validate_message_id(cls, v: str) -> str:
        if not v.startswith("msg_"):
            raise ValueError("Message ID must start with 'msg_'")
        return v

    @model_validator(mode="before")
    @classmethod
    def reject_chain_of_thought(cls, data: Any) -> Any:
        """Strict compliance rule: never accept or persist private model chain-of-thought."""
        if isinstance(data, dict):
            prohibited_keys = ("chain_of_thought", "thinking_process", "raw_reasoning", "cot")
            for key in prohibited_keys:
                if key in data and data[key]:
                    raise ValueError(f"Prohibited field '{key}' detected: private model chain-of-thought must never be persisted.")
        return data


class ChatSession(LimoBaseModel):
    """Persistent conversational thread container."""

    id: str = Field(default_factory=generate_chat_id, description="Stable session ID with 'chat_' prefix")
    project_id: Optional[str] = Field(default=None, description="Associated project ID if scoped to a project")
    title: str = Field(min_length=1, max_length=255, description="Conversational session title")
    mode: FeatureMode = Field(default=FeatureMode.NONE, description="Active creation mode for the thread")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC last message timestamp"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary session configuration")

    @field_validator("id")
    @classmethod
    def validate_chat_id(cls, v: str) -> str:
        if not v.startswith("chat_"):
            raise ValueError("ChatSession ID must start with 'chat_'")
        return v
