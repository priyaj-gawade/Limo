"""User and UserSession domain models for authentication and access control."""

from datetime import datetime, timezone
from typing import Optional
from pydantic import Field, field_validator
from .base import LimoBaseModel
from ..core.ids import generate_prefixed_id


def generate_user_id() -> str:
    return generate_prefixed_id("usr")


class User(LimoBaseModel):
    """Stable application-level user identity."""

    id: str = Field(default_factory=generate_user_id, description="Stable user ID with 'usr_' prefix")
    provider: str = Field(default="google", description="Identity provider (e.g. google, desktop)")
    provider_subject: str = Field(description="Unique stable subject ID from identity provider")
    email: str = Field(description="User primary email address")
    display_name: Optional[str] = Field(default=None, description="User full name or handle")
    avatar_url: Optional[str] = Field(default=None, description="Profile avatar picture URL")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC creation timestamp"
    )
    last_login_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC last authentication timestamp"
    )

    @field_validator("id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not v.startswith("usr_"):
            raise ValueError("User ID must start with 'usr_'")
        return v


class UserSession(LimoBaseModel):
    """Server-side active web session record."""

    session_token: str = Field(description="Opaque cryptographically secure session token")
    user_id: str = Field(description="Owning user ID")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC session creation timestamp"
    )
    expires_at: datetime = Field(description="UTC session expiration timestamp")
    last_accessed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC last request access timestamp"
    )
