"""Chats and Messages REST API router."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from ...models.chat import ChatSession, Message, MessageAttachment
from ...models.enums import FeatureMode, MessageRole
from ...services.chat_service import chat_service

router = APIRouter(prefix="/chats", tags=["Chats"])


class CreateChatSessionRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    mode: FeatureMode = Field(default=FeatureMode.NONE)
    project_id: Optional[str] = Field(default=None)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RenameChatSessionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class AddMessageRequest(BaseModel):
    role: MessageRole = Field(default=MessageRole.USER, description="Message author role")
    content: str = Field(min_length=1, description="Conversational text")
    mode: Optional[FeatureMode] = Field(default=None)
    attachments: List[MessageAttachment] = Field(default_factory=list)
    artifact_ids: List[str] = Field(default_factory=list)
    execution_summary: Optional[str] = Field(default=None)


@router.post("", response_model=ChatSession, status_code=status.HTTP_201_CREATED)
async def create_chat_session(req: CreateChatSessionRequest) -> ChatSession:
    """Create a new conversational session."""
    return chat_service.create_session(
        title=req.title,
        mode=req.mode,
        project_id=req.project_id,
        metadata=req.metadata,
    )


@router.get("", response_model=List[ChatSession])
async def list_chat_sessions(project_id: Optional[str] = None) -> List[ChatSession]:
    """List chat sessions ordered by recency."""
    return chat_service.list_sessions(project_id=project_id)


@router.get("/{session_id}", response_model=ChatSession)
async def get_chat_session(session_id: str) -> ChatSession:
    """Get chat session details."""
    return chat_service.get_session(session_id)


@router.patch("/{session_id}", response_model=ChatSession)
async def rename_chat_session(session_id: str, req: RenameChatSessionRequest) -> ChatSession:
    """Rename a conversation thread."""
    return chat_service.rename_session(session_id, req.title)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(session_id: str) -> None:
    """Delete a conversation session and all its messages."""
    chat_service.delete_session(session_id)


@router.post("/{session_id}/messages", response_model=Message, status_code=status.HTTP_201_CREATED)
async def add_message(session_id: str, req: AddMessageRequest) -> Message:
    """Append a conversational turn (user or assistant) and touch session updated_at."""
    if req.role == MessageRole.ASSISTANT:
        return chat_service.add_assistant_message(
            session_id=session_id,
            content=req.content,
            mode=req.mode,
            artifact_ids=req.artifact_ids,
            execution_summary=req.execution_summary,
        )
    return chat_service.add_user_message(
        session_id=session_id,
        content=req.content,
        mode=req.mode,
        attachments=req.attachments,
    )


@router.get("/{session_id}/messages", response_model=List[Message])
async def get_messages(session_id: str) -> List[Message]:
    """Retrieve full chronological conversation history."""
    return chat_service.get_history(session_id)


class ExecuteTurnRequest(BaseModel):
    content: str = Field(min_length=1, description="User prompt text")
    mode: Optional[FeatureMode] = Field(default=None)
    project_id: Optional[str] = Field(default=None)


@router.post("/{session_id}/turn", response_model=Message, status_code=status.HTTP_200_OK)
async def execute_turn(session_id: str, req: ExecuteTurnRequest) -> Message:
    """Execute a complete agent conversational turn via LimoAgentRuntime and return the assistant Message."""
    from ...agent.runtime import LimoAgentRuntime
    runtime = LimoAgentRuntime()
    return await runtime.execute_turn(
        session_id=session_id,
        user_prompt=req.content,
        mode=req.mode,
        project_id=req.project_id,
    )

