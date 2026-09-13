"""Repository for ChatSession and Message entities."""

from datetime import datetime
import json
import sqlite3
from typing import List, Optional
from ...models.chat import ChatSession, Message, MessageAttachment
from ...models.enums import FeatureMode, MessageRole


class ChatRepository:
    """CRUD repository for Chat Sessions and Messages."""

    @staticmethod
    def create_session(conn: sqlite3.Connection, session: ChatSession) -> ChatSession:
        sql = """
            INSERT INTO chats (id, project_id, title, mode, created_at, updated_at, metadata_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        conn.execute(sql, (
            session.id,
            session.project_id,
            session.title,
            session.mode.value,
            session.created_at.isoformat(),
            session.updated_at.isoformat(),
            json.dumps(session.metadata),
        ))
        return session

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> ChatSession:
        return ChatSession(
            id=row["id"],
            project_id=row["project_id"],
            title=row["title"],
            mode=FeatureMode(row["mode"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            metadata=json.loads(row["metadata_json"]),
        )

    @staticmethod
    def get_session(conn: sqlite3.Connection, session_id: str) -> Optional[ChatSession]:
        sql = "SELECT id, project_id, title, mode, created_at, updated_at, metadata_json FROM chats WHERE id = ?"
        row = conn.execute(sql, (session_id,)).fetchone()
        if not row:
            return None
        return ChatRepository._row_to_model(row)

    @staticmethod
    def list_sessions(conn: sqlite3.Connection, project_id: Optional[str] = None) -> List[ChatSession]:
        if project_id:
            sql = "SELECT id, project_id, title, mode, created_at, updated_at, metadata_json FROM chats WHERE project_id = ? ORDER BY updated_at DESC"
            rows = conn.execute(sql, (project_id,)).fetchall()
        else:
            sql = "SELECT id, project_id, title, mode, created_at, updated_at, metadata_json FROM chats ORDER BY updated_at DESC"
            rows = conn.execute(sql).fetchall()

        return [ChatRepository._row_to_model(row) for row in rows]

    @staticmethod
    def update_session(conn: sqlite3.Connection, session: ChatSession) -> Optional[ChatSession]:
        sql = """
            UPDATE chats
            SET title = ?, mode = ?, updated_at = ?, metadata_json = ?
            WHERE id = ?
        """
        cur = conn.execute(sql, (
            session.title,
            session.mode.value,
            session.updated_at.isoformat(),
            json.dumps(session.metadata),
            session.id,
        ))
        if cur.rowcount == 0:
            return None
        return session

    @staticmethod
    def delete_session(conn: sqlite3.Connection, session_id: str) -> bool:
        sql = "DELETE FROM chats WHERE id = ?"
        cur = conn.execute(sql, (session_id,))
        return cur.rowcount > 0

    @staticmethod
    def add_message(conn: sqlite3.Connection, message: Message) -> Message:
        sql = """
            INSERT INTO messages (
                id, session_id, role, content, mode,
                attachments_json, artifact_ids_json, execution_summary, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        attachments_data = [att.model_dump() for att in message.attachments]
        conn.execute(sql, (
            message.id,
            message.session_id,
            message.role.value,
            message.content,
            message.mode.value if message.mode else None,
            json.dumps(attachments_data),
            json.dumps(message.artifact_ids),
            message.execution_summary,
            message.created_at.isoformat(),
        ))

        # Also touch the session's updated_at
        conn.execute(
            "UPDATE chats SET updated_at = ? WHERE id = ?",
            (message.created_at.isoformat(), message.session_id)
        )
        return message

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> Message:
        raw_attachments = json.loads(row["attachments_json"])
        attachments = [MessageAttachment(**att) for att in raw_attachments]
        return Message(
            id=row["id"],
            session_id=row["session_id"],
            role=MessageRole(row["role"]),
            content=row["content"],
            mode=FeatureMode(row["mode"]) if row["mode"] else None,
            attachments=attachments,
            artifact_ids=json.loads(row["artifact_ids_json"]),
            execution_summary=row["execution_summary"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    @staticmethod
    def get_messages(conn: sqlite3.Connection, session_id: str) -> List[Message]:
        sql = """
            SELECT id, session_id, role, content, mode,
                   attachments_json, artifact_ids_json, execution_summary, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY created_at ASC
        """
        rows = conn.execute(sql, (session_id,)).fetchall()
        return [ChatRepository._row_to_message(row) for row in rows]

    @staticmethod
    def delete_message(conn: sqlite3.Connection, message_id: str) -> bool:
        sql = "DELETE FROM messages WHERE id = ?"
        cur = conn.execute(sql, (message_id,))
        return cur.rowcount > 0
