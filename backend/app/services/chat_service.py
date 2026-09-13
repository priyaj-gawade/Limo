"""Chat and Message management business service."""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional

from ..db.connection import get_connection
from ..db.repositories.artifact_repo import ArtifactRepository
from ..db.repositories.chat_repo import ChatRepository
from ..db.repositories.project_repo import ProjectRepository
from ..exceptions import EntityNotFoundError
from ..models.chat import ChatSession, Message, MessageAttachment
from ..models.enums import FeatureMode, MessageRole

logger = logging.getLogger("limo.services.chat")


class ChatService:
    """Business service managing ChatGPT-style conversational sessions and turns."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path

    def create_session(
        self,
        title: Optional[str] = None,
        mode: FeatureMode = FeatureMode.NONE,
        project_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ChatSession:
        """Create a new conversational session container."""
        clean_title = title.strip() if title else "New Conversation"

        with get_connection(self.db_path) as conn:
            if project_id:
                project = ProjectRepository.get_project(conn, project_id)
                if not project:
                    raise EntityNotFoundError("Project", project_id)

            session = ChatSession(
                title=clean_title,
                mode=mode,
                project_id=project_id,
                metadata=metadata or {},
            )
            created = ChatRepository.create_session(conn, session)
            logger.info("Created chat session '%s' (id: %s, mode: %s)", created.title, created.id, created.mode)
            return created

    def get_session(self, session_id: str) -> ChatSession:
        """Retrieve session by ID or raise EntityNotFoundError."""
        with get_connection(self.db_path) as conn:
            session = ChatRepository.get_session(conn, session_id)
            if not session:
                raise EntityNotFoundError("ChatSession", session_id)
            return session

    def list_sessions(self, project_id: Optional[str] = None) -> List[ChatSession]:
        """List sessions ordered by most recently updated."""
        with get_connection(self.db_path) as conn:
            return ChatRepository.list_sessions(conn, project_id)

    def rename_session(self, session_id: str, new_title: str) -> ChatSession:
        """Rename an existing conversation thread."""
        clean_title = new_title.strip()
        if not clean_title:
            raise ValueError("Chat session title cannot be empty")

        with get_connection(self.db_path) as conn:
            session = ChatRepository.get_session(conn, session_id)
            if not session:
                raise EntityNotFoundError("ChatSession", session_id)

            session.title = clean_title
            session.updated_at = datetime.now(timezone.utc)
            updated = ChatRepository.update_session(conn, session)
            if not updated:
                raise EntityNotFoundError("ChatSession", session_id)

            logger.info("Renamed chat session (id: %s) to '%s'", session_id, clean_title)
            return updated

    def delete_session(self, session_id: str) -> bool:
        """Delete a chat session and all cascading messages."""
        with get_connection(self.db_path) as conn:
            session = ChatRepository.get_session(conn, session_id)
            if not session:
                raise EntityNotFoundError("ChatSession", session_id)

            deleted = ChatRepository.delete_session(conn, session_id)
            logger.info("Deleted chat session (id: %s)", session_id)
            return deleted

    def add_user_message(
        self,
        session_id: str,
        content: str,
        mode: Optional[FeatureMode] = None,
        attachments: Optional[List[MessageAttachment]] = None,
    ) -> Message:
        """Append a user conversational turn and touch chat.updated_at."""
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Message content cannot be empty")

        with get_connection(self.db_path) as conn:
            session = ChatRepository.get_session(conn, session_id)
            if not session:
                raise EntityNotFoundError("ChatSession", session_id)

            message = Message(
                session_id=session_id,
                role=MessageRole.USER,
                content=clean_content,
                mode=mode or session.mode,
                attachments=attachments or [],
            )

            # Persist message and explicitly touch session updated_at
            created = ChatRepository.add_message(conn, message)
            logger.info("Added user message to chat '%s' (msg_id: %s)", session_id, created.id)
            return created

    def add_assistant_message(
        self,
        session_id: str,
        content: str,
        mode: Optional[FeatureMode] = None,
        artifact_ids: Optional[List[str]] = None,
        execution_summary: Optional[str] = None,
    ) -> Message:
        """Append an assistant response turn and touch chat.updated_at.

        Compliance notice: Never includes or accepts private model chain-of-thought.
        Only public safe execution summaries are permitted.
        """
        clean_content = content.strip()
        if not clean_content:
            raise ValueError("Message content cannot be empty")

        with get_connection(self.db_path) as conn:
            session = ChatRepository.get_session(conn, session_id)
            if not session:
                raise EntityNotFoundError("ChatSession", session_id)

            message = Message(
                session_id=session_id,
                role=MessageRole.ASSISTANT,
                content=clean_content,
                mode=mode or session.mode,
                artifact_ids=artifact_ids or [],
                execution_summary=execution_summary,
            )

            created = ChatRepository.add_message(conn, message)
            self._hydrate_artifacts(conn, [created])
            logger.info("Added assistant message to chat '%s' (msg_id: %s)", session_id, created.id)
            return created

    def _hydrate_artifacts(self, conn, messages: List[Message]) -> List[Message]:
        """Resolve full Artifact models for any message with referenced artifact IDs."""
        for msg in messages:
            if msg.artifact_ids:
                resolved = []
                for art_id in msg.artifact_ids:
                    art = ArtifactRepository.get_artifact(conn, art_id)
                    if art:
                        resolved.append(art)
                msg.artifacts = resolved
        return messages

    def get_history(self, session_id: str) -> List[Message]:
        """Retrieve full chronological conversation history for a session."""
        with get_connection(self.db_path) as conn:
            session = ChatRepository.get_session(conn, session_id)
            if not session:
                raise EntityNotFoundError("ChatSession", session_id)

            messages = ChatRepository.get_messages(conn, session_id)
            return self._hydrate_artifacts(conn, messages)


chat_service = ChatService()
