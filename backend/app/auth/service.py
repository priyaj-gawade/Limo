"""Authentication Service managing Google OAuth, user resolution, and session lifecycle."""

from datetime import datetime, timedelta, timezone
import logging
import secrets
from typing import Any, Dict, Optional
import urllib.parse

import httpx

from ..db.connection import get_connection
from ..db.repositories.user_repo import UserRepository
from ..models.user import User, UserSession
from .config import AuthConfig, auth_config

logger = logging.getLogger("limo.auth.service")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class AuthService:
    """Handles Google OAuth authorization, token verification, and session state."""

    def __init__(self, config: Optional[AuthConfig] = None, db_path: Optional[str] = None):
        self.config = config or auth_config
        self.db_path = db_path

    def generate_auth_url(self, state: str) -> str:
        """Construct the Google OAuth authorization redirect URL."""
        if not self.config.google_client_id:
            raise RuntimeError("Google Client ID is not configured")

        params = {
            "client_id": self.config.google_client_id,
            "redirect_uri": self.config.google_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "select_account",
        }
        return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code with Google token endpoint."""
        if not self.config.google_client_id or not self.config.google_client_secret:
            raise RuntimeError("Google OAuth client credentials are not configured")

        data = {
            "client_id": self.config.google_client_id,
            "client_secret": self.config.google_client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.config.google_redirect_uri,
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(GOOGLE_TOKEN_URL, data=data)
            if token_resp.status_code != 200:
                logger.error("Google token exchange failed: %d - %s", token_resp.status_code, token_resp.text)
                raise ValueError("Failed to exchange authorization code with Google")

            return token_resp.json()

    async def fetch_google_user_profile(self, access_token: str) -> Dict[str, Any]:
        """Fetch user identity and profile from Google userinfo endpoint."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            userinfo_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if userinfo_resp.status_code != 200:
                logger.error("Failed to retrieve Google userinfo: %d", userinfo_resp.status_code)
                raise ValueError("Failed to retrieve user profile from Google")

            return userinfo_resp.json()

    async def verify_google_code(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code with Google and retrieve user identity."""
        tokens = await self.exchange_code_for_tokens(code)
        access_token = tokens.get("access_token")
        if not access_token:
            raise ValueError("Google token exchange returned no access_token")

        return await self.fetch_google_user_profile(access_token)

    def resolve_user(
        self,
        provider_subject: str,
        email: str,
        display_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> User:
        """Resolve or persist application user identity."""
        with get_connection(self.db_path) as conn:
            return UserRepository.get_or_create_user(
                conn=conn,
                provider_subject=provider_subject,
                email=email,
                display_name=display_name,
                avatar_url=avatar_url,
                provider="google",
            )

    def create_user_session(self, user_id: str) -> UserSession:
        """Create and persist a secure session token with expiration, returning UserSession."""
        session_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(days=self.config.session_expiry_days)

        with get_connection(self.db_path) as conn:
            return UserRepository.create_session(
                conn=conn,
                session_token=session_token,
                user_id=user_id,
                expires_at=expires_at,
            )

    def create_session(self, user_id: str) -> str:
        """Create and persist a secure session token with expiration, returning token string."""
        session = self.create_user_session(user_id)
        return session.session_token

    def validate_session(self, session_token: str) -> Optional[User]:
        """Validate session token, reject expired sessions, and touch last access time."""
        now = datetime.now(timezone.utc)
        with get_connection(self.db_path) as conn:
            session = UserRepository.get_session(conn, session_token)
            if not session:
                return None

            if session.expires_at < now:
                logger.info("Session '%s' has expired, removing from SQLite", session_token[:8])
                UserRepository.delete_session(conn, session_token)
                return None

            UserRepository.touch_session(conn, session_token)
            return UserRepository.get_user_by_id(conn, session.user_id)

    def invalidate_session(self, session_token: str) -> bool:
        """Invalidate active session on logout."""
        with get_connection(self.db_path) as conn:
            return UserRepository.delete_session(conn, session_token)


auth_service = AuthService()
