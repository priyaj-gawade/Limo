"""Chat session management tool for Limo Agent Infrastructure."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from ..contracts import BaseTool, ToolResult, PermissionType
from ..context import AgentContext
from ...services.chat_service import ChatService, chat_service
from ...exceptions import EntityNotFoundError


class ChatArgs(BaseModel):
    action: str = Field(description="Action to perform: 'get_history', 'create_session', or 'list_sessions'")
    session_id: Optional[str] = Field(default=None, description="Session ID (defaults to active context)")
    limit: Optional[int] = Field(default=20, description="Max messages to retrieve for get_history")
    title: Optional[str] = Field(default=None, description="Title for create_session")
    project_id: Optional[str] = Field(default=None, description="Project ID for create_session")


class ChatTool(BaseTool):
    """Inspect and manage chat conversations."""

    name: str = "chat_tool"
    description: str = "Query chat history or manage conversation sessions."
    permission_type: PermissionType = PermissionType.READ

    def __init__(self, service: Optional[ChatService] = None) -> None:
        self.service = service or chat_service

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return ChatArgs.model_json_schema()

    async def execute(self, args: Dict[str, Any], context: Optional[AgentContext] = None) -> ToolResult:
        try:
            parsed = ChatArgs(**args)
        except Exception as e:
            return ToolResult.fail(f"Invalid arguments for chat_tool: {str(e)}")

        session_id = parsed.session_id or (context.session_id if context else None)

        if parsed.action == "get_history":
            if not session_id:
                return ToolResult.fail("Missing required 'session_id'")
            try:
                history = self.service.get_history(session_id)
                if parsed.limit and len(history) > parsed.limit:
                    history = history[-parsed.limit:]
                formatted = [
                    {
                        "id": m.id,
                        "role": m.role.value if hasattr(m.role, "value") else str(m.role),
                        "content": m.content,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
                    }
                    for m in history
                ]
                return ToolResult.ok({"session_id": session_id, "messages": formatted, "count": len(formatted)})
            except EntityNotFoundError:
                return ToolResult.fail(f"Chat session '{session_id}' not found")

        elif parsed.action == "list_sessions":
            project_id = parsed.project_id or (context.project_id if context else None)
            sessions = self.service.list_sessions(project_id=project_id)
            summaries = [
                {
                    "id": s.id,
                    "title": s.title,
                    "mode": s.mode.value if hasattr(s.mode, "value") else str(s.mode),
                    "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                }
                for s in sessions
            ]
            return ToolResult.ok({"sessions": summaries, "count": len(summaries)})

        elif parsed.action == "create_session":
            project_id = parsed.project_id or (context.project_id if context else None)
            try:
                session = self.service.create_session(
                    title=parsed.title,
                    project_id=project_id,
                )
                return ToolResult.ok({"id": session.id, "title": session.title, "created": True})
            except Exception as e:
                return ToolResult.fail(f"Failed to create chat session: {str(e)}")

        else:
            return ToolResult.fail(
                f"Unknown action '{parsed.action}'. Supported: 'get_history', 'list_sessions', 'create_session'"
            )
