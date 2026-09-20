"""Authentication REST API router exposing Google OAuth and session lifecycle."""

import logging
import secrets
from typing import Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse

from ...auth.config import auth_config
from ...auth.dependencies import get_current_user
from ...auth.service import auth_service
from ...models.user import User

logger = logging.getLogger("limo.api.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/login")
async def login(response: Response):
    """Initiate Google OAuth flow, returning authorization URL and CSRF state."""
    state = secrets.token_urlsafe(16)
    auth_url = auth_service.generate_auth_url(state=state)

    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        samesite="lax",
        max_age=600,
        secure=auth_config.is_web_surface,
    )
    response.set_cookie(
        key="limo_oauth_state",
        value=state,
        httponly=True,
        samesite="lax",
        max_age=600,
        secure=auth_config.is_web_surface,
    )
    return {
        "authorization_url": auth_url,
        "state": state,
    }


@router.get("/google/login")
async def google_login(response: Response, redirect: Optional[str] = Query(None)):
    """Initiate Google OAuth 2.0 sign-in with direct 307 redirect to Google."""
    state = secrets.token_urlsafe(16)
    auth_url = auth_service.generate_auth_url(state=state)

    resp = RedirectResponse(url=auth_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    resp.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        samesite="lax",
        max_age=600,
        secure=auth_config.is_web_surface,
    )
    resp.set_cookie(
        key="limo_oauth_state",
        value=state,
        httponly=True,
        samesite="lax",
        max_age=600,
        secure=auth_config.is_web_surface,
    )
    return resp


async def _process_oauth_callback(
    code: str,
    state: str,
    expected_state: Optional[str],
) -> tuple[User, str]:
    """Helper to validate state, verify code with Google, resolve user, and create session."""
    if expected_state and state != expected_state:
        logger.error("OAuth state mismatch: received '%s', expected '%s'", state, expected_state)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OAuth state validation failed (CSRF check)",
        )

    try:
        userinfo = await auth_service.verify_google_code(code)
    except Exception as e:
        logger.error("Google authentication failed during code exchange: %s", e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Google authentication failed: {str(e)}",
        )

    sub = userinfo.get("sub")
    email = userinfo.get("email")
    if not sub or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google profile returned incomplete identity data",
        )

    name = userinfo.get("name")
    picture = userinfo.get("picture")

    user = auth_service.resolve_user(
        provider_subject=sub,
        email=email,
        display_name=name,
        avatar_url=picture,
    )
    session_token = auth_service.create_session(user.id)
    return user, session_token


@router.get("/callback", response_model=User)
async def callback(
    response: Response,
    code: str = Query(..., description="Google OAuth authorization code"),
    state: str = Query(..., description="OAuth state parameter"),
    oauth_state: Optional[str] = Cookie(None),
    limo_oauth_state: Optional[str] = Cookie(None),
):
    """Handle OAuth redirect callback, establish session, and return User model."""
    expected_state = oauth_state or limo_oauth_state
    user, session_token = await _process_oauth_callback(code, state, expected_state)

    response.set_cookie(
        key="limo_session",
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * auth_config.session_expiry_days,
        secure=auth_config.is_web_surface,
    )
    response.delete_cookie("oauth_state")
    response.delete_cookie("limo_oauth_state")
    return user


@router.get("/google/callback")
async def google_callback(
    request: Request,
    response: Response,
    code: str = Query(..., description="Google OAuth authorization code"),
    state: str = Query(..., description="OAuth state parameter"),
    oauth_state: Optional[str] = Cookie(None),
    limo_oauth_state: Optional[str] = Cookie(None),
):
    """Handle Google OAuth redirect, establish session, and redirect to frontend."""
    expected_state = limo_oauth_state or oauth_state
    user, session_token = await _process_oauth_callback(code, state, expected_state)

    redirect_dest = auth_config.google_redirect_uri.split("/auth/callback")[0] or "/"
    resp = RedirectResponse(url=redirect_dest, status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(
        key="limo_session",
        value=session_token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * auth_config.session_expiry_days,
        secure=auth_config.is_web_surface,
    )
    resp.delete_cookie("limo_oauth_state")
    resp.delete_cookie("oauth_state")
    return resp


@router.get("/me", response_model=User)
async def get_my_profile(current_user: User = Depends(get_current_user)) -> User:
    """Retrieve the current authenticated user identity."""
    return current_user


@router.post("/logout")
async def logout(
    response: Response,
    limo_session: Optional[str] = Cookie(None),
):
    """Invalidate current session and clear HttpOnly session cookie."""
    if limo_session:
        auth_service.invalidate_session(limo_session)

    response.delete_cookie("limo_session")
    return {"status": "logged_out", "message": "Session invalidated successfully"}
