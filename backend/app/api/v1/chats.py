"""Chats and Messages REST API router with resource authorization."""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field

from ...auth.config import auth_config
from ...auth.dependencies import authorize_resource, get_current_user
from ...models.chat import ChatSession, Message, MessageAttachment
from ...models.enums import FeatureMode, MessageRole
from ...models.user import User
from ...services.chat_service import chat_service
from ...services.project_service import project_service

router = APIRouter(prefix="/chats", tags=["Chats"])


def _authorize_chat_session(session: ChatSession, current_user: User) -> None:
    """Check multi-tenant authorization for a chat session."""
    if auth_config.is_desktop_surface:
        return
    owner_id = session.metadata.get("user_id") if isinstance(session.metadata, dict) else None
    if not owner_id and session.project_id:
        try:
            proj = project_service.get_project(session.project_id)
            owner_id = proj.user_id
        except Exception:
            pass
    authorize_resource(owner_id, current_user)


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
async def create_chat_session(
    req: CreateChatSessionRequest,
    current_user: User = Depends(get_current_user),
) -> ChatSession:
    """Create a new conversational session."""
    if req.project_id:
        proj = project_service.get_project(req.project_id)
        authorize_resource(proj.user_id, current_user)

    metadata = dict(req.metadata)
    metadata["user_id"] = current_user.id

    return chat_service.create_session(
        title=req.title,
        mode=req.mode,
        project_id=req.project_id,
        metadata=metadata,
    )


@router.get("", response_model=List[ChatSession])
async def list_chat_sessions(
    project_id: Optional[str] = Query(None, description="Filter chat sessions by project"),
    current_user: User = Depends(get_current_user),
) -> List[ChatSession]:
    """List chat sessions ordered by recency, scoped to user on web surface."""
    if project_id:
        proj = project_service.get_project(project_id)
        authorize_resource(proj.user_id, current_user)
        return chat_service.list_sessions(project_id=project_id)

    sessions = chat_service.list_sessions(project_id=None)
    if auth_config.is_web_surface:
        user_projects = {p.id for p in project_service.list_projects(user_id=current_user.id)}
        sessions = [
            s for s in sessions
            if s.metadata.get("user_id") == current_user.id or (s.project_id and s.project_id in user_projects)
        ]
    return sessions


@router.get("/{session_id}", response_model=ChatSession)
async def get_chat_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> ChatSession:
    """Get chat session details."""
    session = chat_service.get_session(session_id)
    _authorize_chat_session(session, current_user)
    return session


@router.patch("/{session_id}", response_model=ChatSession)
async def rename_chat_session(
    session_id: str,
    req: RenameChatSessionRequest,
    current_user: User = Depends(get_current_user),
) -> ChatSession:
    """Rename a conversation thread."""
    session = chat_service.get_session(session_id)
    _authorize_chat_session(session, current_user)
    return chat_service.rename_session(session_id, req.title)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a conversation session and all its messages."""
    session = chat_service.get_session(session_id)
    _authorize_chat_session(session, current_user)
    chat_service.delete_session(session_id)


@router.post("/{session_id}/messages", response_model=Message, status_code=status.HTTP_201_CREATED)
async def add_message(
    session_id: str,
    req: AddMessageRequest,
    current_user: User = Depends(get_current_user),
) -> Message:
    """Append a conversational turn (user or assistant) and touch session updated_at."""
    session = chat_service.get_session(session_id)
    _authorize_chat_session(session, current_user)

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
async def get_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
) -> List[Message]:
    """Retrieve full chronological conversation history."""
    session = chat_service.get_session(session_id)
    _authorize_chat_session(session, current_user)
    return chat_service.get_history(session_id)


class ExecuteTurnRequest(BaseModel):
    content: str = Field(min_length=1, description="User prompt text")
    mode: Optional[FeatureMode] = Field(default=None)
    project_id: Optional[str] = Field(default=None)
    attachments: Optional[List[MessageAttachment]] = Field(default=None, description="Turn attachments")
    source_ids: Optional[List[str]] = Field(default=None, description="Explicit source IDs linked to this turn")
    voice_config: Optional[Dict[str, Any]] = Field(default=None, description="Selected voice parameters {provider, voice_id, speed}")


@router.post("/{session_id}/turn", response_model=Message, status_code=status.HTTP_200_OK)
async def execute_turn(
    session_id: str,
    req: ExecuteTurnRequest,
    current_user: User = Depends(get_current_user),
) -> Message:
    """Execute a complete agent conversational turn via LimoAgentRuntime and return the assistant Message."""
    session = chat_service.get_session(session_id)
    _authorize_chat_session(session, current_user)

    if req.project_id:
        proj = project_service.get_project(req.project_id)
        authorize_resource(proj.user_id, current_user)

    from ...agent.runtime import LimoAgentRuntime
    runtime = LimoAgentRuntime()
    return await runtime.execute_turn(
        session_id=session_id,
        user_prompt=req.content,
        mode=req.mode,
        project_id=req.project_id,
        attachments=req.attachments,
        source_ids=req.source_ids,
        voice_config=req.voice_config,
    )

