"""FastAPI dependencies for authentication and resource authorization."""

from datetime import datetime, timezone
import logging
from typing import Optional
from fastapi import Cookie, Depends, Header, HTTPException, Request, status

from ..models.user import User
from .config import auth_config
from .service import auth_service

logger = logging.getLogger("limo.auth.dependencies")

DESKTOP_USER = User(
    id="usr_desktop",
    provider="desktop",
    provider_subject="desktop_local",
    email="desktop@limo.local",
    display_name="Local Desktop User",
    created_at=datetime.now(timezone.utc),
    last_login_at=datetime.now(timezone.utc),
)


async def get_current_user(
    request: Request,
    limo_session: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> User:
    """Enforce authentication boundary across desktop vs web surfaces."""
    token = limo_session
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()

    if token:
        user = auth_service.validate_session(token)
        if user:
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session is invalid or expired. Please sign in again.",
        )

    # 1. If authentication is required (web surface OR OAuth is configured), fail closed
    if auth_config.is_auth_required:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required to access this resource",
        )

    # 2. Pure offline desktop surface without OAuth credentials
    return DESKTOP_USER


async def get_optional_user(
    request: Request,
    limo_session: Optional[str] = Cookie(None),
    authorization: Optional[str] = Header(None),
) -> Optional[User]:
    """Retrieve user context if available without raising 401."""
    token = limo_session
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()

    if token:
        user = auth_service.validate_session(token)
        if user:
            return user

    if not auth_config.is_auth_required and auth_config.is_desktop_surface:
        return DESKTOP_USER

    return None


def authorize_resource(owner_user_id: Optional[str], current_user: User) -> None:
    """Enforce multi-tenant resource isolation."""
    if not auth_config.is_auth_required and auth_config.is_desktop_surface:
        return

    # If resource has an explicit owner and current user does not match, reject
    if owner_user_id and owner_user_id != current_user.id:
        logger.warning(
            "Access denied: User '%s' attempted to access resource owned by '%s'",
            current_user.id,
            owner_user_id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this resource",
        )
