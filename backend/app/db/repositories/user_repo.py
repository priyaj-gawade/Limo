"""Repository for User and UserSession entities."""

from datetime import datetime, timezone
import sqlite3
from typing import Optional
from ...models.user import User, UserSession, generate_user_id


class UserRepository:
    """CRUD repository for user identity and authenticated sessions."""

    @staticmethod
    def create_or_update_user(conn: sqlite3.Connection, user: User) -> User:
        now = datetime.now(timezone.utc).isoformat()
        row = conn.execute(
            "SELECT * FROM users WHERE provider_subject = ? OR id = ?",
            (user.provider_subject, user.id)
        ).fetchone()

        if row:
            conn.execute(
                """
                UPDATE users
                SET email = ?, display_name = COALESCE(?, display_name),
                    avatar_url = COALESCE(?, avatar_url), last_login_at = ?
                WHERE id = ?
                """,
                (user.email, user.display_name, user.avatar_url, now, row["id"])
            )
            return User(
                id=row["id"],
                provider=row["provider"],
                provider_subject=row["provider_subject"],
                email=user.email,
                display_name=user.display_name or row["display_name"],
                avatar_url=user.avatar_url or row["avatar_url"],
                created_at=datetime.fromisoformat(row["created_at"]),
                last_login_at=datetime.fromisoformat(now),
            )

        user_id = user.id or generate_user_id()
        conn.execute(
            """
            INSERT INTO users (id, provider, provider_subject, email, display_name, avatar_url, created_at, last_login_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, user.provider, user.provider_subject, user.email, user.display_name, user.avatar_url, now, now)
        )
        return User(
            id=user_id,
            provider=user.provider,
            provider_subject=user.provider_subject,
            email=user.email,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            created_at=datetime.fromisoformat(now),
            last_login_at=datetime.fromisoformat(now),
        )

    @staticmethod
    def get_or_create_user(
        conn: sqlite3.Connection,
        provider_subject: str,
        email: str,
        display_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        provider: str = "google",
    ) -> User:
        now = datetime.now(timezone.utc).isoformat()
        row = conn.execute(
            "SELECT * FROM users WHERE provider_subject = ?",
            (provider_subject,)
        ).fetchone()

        if row:
            conn.execute(
                """
                UPDATE users
                SET email = ?, display_name = COALESCE(?, display_name),
                    avatar_url = COALESCE(?, avatar_url), last_login_at = ?
                WHERE id = ?
                """,
                (email, display_name, avatar_url, now, row["id"])
            )
            return User(
                id=row["id"],
                provider=row["provider"],
                provider_subject=row["provider_subject"],
                email=email,
                display_name=display_name or row["display_name"],
                avatar_url=avatar_url or row["avatar_url"],
                created_at=datetime.fromisoformat(row["created_at"]),
                last_login_at=datetime.fromisoformat(now),
            )

        user_id = generate_user_id()
        conn.execute(
            """
            INSERT INTO users (id, provider, provider_subject, email, display_name, avatar_url, created_at, last_login_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, provider, provider_subject, email, display_name, avatar_url, now, now)
        )
        return User(
            id=user_id,
            provider=provider,
            provider_subject=provider_subject,
            email=email,
            display_name=display_name,
            avatar_url=avatar_url,
            created_at=datetime.fromisoformat(now),
            last_login_at=datetime.fromisoformat(now),
        )

    @staticmethod
    def get_user_by_id(conn: sqlite3.Connection, user_id: str) -> Optional[User]:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if not row:
            return None
        return User(
            id=row["id"],
            provider=row["provider"],
            provider_subject=row["provider_subject"],
            email=row["email"],
            display_name=row["display_name"],
            avatar_url=row["avatar_url"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_login_at=datetime.fromisoformat(row["last_login_at"]),
        )

    @staticmethod
    def create_session(
        conn: sqlite3.Connection,
        session_token: str,
        user_id: str,
        expires_at: datetime,
    ) -> UserSession:
        now = datetime.now(timezone.utc)
        conn.execute(
            """
            INSERT INTO user_sessions (session_token, user_id, created_at, expires_at, last_accessed_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (session_token, user_id, now.isoformat(), expires_at.isoformat(), now.isoformat())
        )
        return UserSession(
            session_token=session_token,
            user_id=user_id,
            created_at=now,
            expires_at=expires_at,
            last_accessed_at=now,
        )

    @staticmethod
    def get_session(conn: sqlite3.Connection, session_token: str) -> Optional[UserSession]:
        row = conn.execute(
            "SELECT * FROM user_sessions WHERE session_token = ?",
            (session_token,)
        ).fetchone()
        if not row:
            return None
        return UserSession(
            session_token=row["session_token"],
            user_id=row["user_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            expires_at=datetime.fromisoformat(row["expires_at"]),
            last_accessed_at=datetime.fromisoformat(row["last_accessed_at"]),
        )

    @staticmethod
    def touch_session(conn: sqlite3.Connection, session_token: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE user_sessions SET last_accessed_at = ? WHERE session_token = ?",
            (now, session_token)
        )

    @staticmethod
    def delete_session(conn: sqlite3.Connection, session_token: str) -> bool:
        cur = conn.execute("DELETE FROM user_sessions WHERE session_token = ?", (session_token,))
        return cur.rowcount > 0

    @staticmethod
    def delete_expired_sessions(conn: sqlite3.Connection) -> int:
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute("DELETE FROM user_sessions WHERE expires_at < ?", (now,))
        return cur.rowcount
