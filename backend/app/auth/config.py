"""Authentication and Surface Configuration for Limo (Phase D9.5)."""

import json
import logging
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

logger = logging.getLogger("limo.auth.config")


class AuthConfig(BaseModel):
    """Configuration governing surface mode and Google OAuth integration."""

    surface: str = "desktop"  # "desktop" or "web"
    google_client_id: Optional[str] = None
    google_client_secret: Optional[str] = None
    google_redirect_uri: str = "http://localhost:5190/auth/callback"
    session_expiry_days: int = 7

    @property
    def has_oauth_configured(self) -> bool:
        """Check if Google OAuth credentials are provided."""
        return bool(
            self.google_client_id
            and self.google_client_id.strip()
            and self.google_client_secret
            and self.google_client_secret.strip()
        )

    @property
    def is_web_surface(self) -> bool:
        return self.surface.lower() == "web"

    @property
    def is_desktop_surface(self) -> bool:
        return self.surface.lower() == "desktop"

    @property
    def is_auth_required(self) -> bool:
        """Authentication is required if on web surface OR if Google OAuth is configured."""
        return self.is_web_surface or self.has_oauth_configured

    def validate_surface_requirements(self) -> None:
        """Enforce fail-closed requirement for web surface."""
        if self.is_web_surface:
            if not self.has_oauth_configured:
                raise ValueError(
                    "Google OAuth client_id and client_secret must be configured when LIMO_SURFACE=web. "
                    "Authentication must fail closed."
                )


def load_auth_config(repo_root: Optional[Path] = None) -> AuthConfig:
    """Load auth config from environment variables or local credentials/google_auth.json."""
    surface = os.getenv("LIMO_SURFACE", "desktop").lower()

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:5190/auth/callback")

    # Fallback to credentials/google_auth.json if environment variables are not set
    if not client_id or not client_secret:
        root = repo_root or Path(__file__).resolve().parent.parent.parent.parent
        creds_file = root / "credentials" / "google_auth.json"
        if creds_file.is_file():
            try:
                data = json.loads(creds_file.read_text(encoding="utf-8"))
                web_data = data.get("web", data)
                client_id = client_id or web_data.get("client_id")
                client_secret = client_secret or web_data.get("client_secret")
                uris = web_data.get("redirect_uris", [])
                if uris and not os.getenv("GOOGLE_REDIRECT_URI"):
                    # Prefer frontend callback if present
                    redirect_uri = next((u for u in uris if "callback" in u), uris[0])
            except Exception as e:
                logger.warning("Failed to parse credentials/google_auth.json: %s", e)

    config = AuthConfig(
        surface=surface,
        google_client_id=client_id,
        google_client_secret=client_secret,
        google_redirect_uri=redirect_uri,
    )

    # Fail-closed enforcement on web surface
    if config.is_web_surface:
        try:
            config.validate_surface_requirements()
        except ValueError as e:
            raise RuntimeError(str(e)) from e

    return config


auth_config = load_auth_config()
