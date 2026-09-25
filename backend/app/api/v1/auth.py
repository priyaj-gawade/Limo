"""Authentication REST API router exposing Google OAuth and session lifecycle."""

import json
import logging
import secrets
from typing import Optional
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse

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
    try:
        auth_url = auth_service.generate_auth_url(state=state)
    except Exception as e:
        logger.error("Failed to generate Google OAuth URL: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth is not properly configured: {str(e)}",
        )

    cookie_kwargs = {
        "httponly": True,
        "samesite": "lax",
        "max_age": 600,
        "secure": auth_config.is_web_surface,
    }
    if auth_config.cookie_domain:
        cookie_kwargs["domain"] = auth_config.cookie_domain

    response.set_cookie(key="oauth_state", value=state, **cookie_kwargs)
    response.set_cookie(key="limo_oauth_state", value=state, **cookie_kwargs)
    return {
        "authorization_url": auth_url,
        "state": state,
    }


@router.get("/google/login")
async def google_login(response: Response, redirect: Optional[str] = Query(None)):
    """Initiate Google OAuth 2.0 sign-in with direct 307 redirect to Google."""
    state = secrets.token_urlsafe(16)
    try:
        auth_url = auth_service.generate_auth_url(state=state)
    except Exception as e:
        logger.error("Failed to generate Google OAuth URL: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth is not properly configured: {str(e)}",
        )

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

    session_cookie_kwargs = {
        "httponly": True,
        "samesite": "lax",
        "max_age": 60 * 60 * 24 * auth_config.session_expiry_days,
        "secure": auth_config.is_web_surface,
    }
    if auth_config.cookie_domain:
        session_cookie_kwargs["domain"] = auth_config.cookie_domain

    response.set_cookie(
        key="limo_session",
        value=session_token,
        **session_cookie_kwargs,
    )
    del_kwargs = {"domain": auth_config.cookie_domain} if auth_config.cookie_domain else {}
    response.delete_cookie("oauth_state", **del_kwargs)
    response.delete_cookie("limo_oauth_state", **del_kwargs)
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
    """Handle Google OAuth redirect, establish session, and notify frontend popup or redirect."""
    expected_state = limo_oauth_state or oauth_state
    try:
        user, session_token = await _process_oauth_callback(code, state, expected_state)
    except Exception as e:
        logger.error("OAuth callback processing error: %s", e)
        error_msg = str(getattr(e, "detail", e))
        error_html = f"""<!DOCTYPE html>
<html>
<head><title>Authentication Failed</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, sans-serif; text-align: center; padding: 2rem; background: #0f1117; color: #ef4444;">
  <h3>Sign-in Failed</h3>
  <p>{error_msg}</p>
  <script>
    if (window.opener) {{
      try {{
        window.opener.postMessage({{ type: 'LIMO_AUTH_ERROR', error: {json.dumps(error_msg)} }}, '*');
      }} catch(err) {{}}
      setTimeout(() => {{ window.close(); }}, 2500);
    }}
  </script>
</body>
</html>"""
        return HTMLResponse(content=error_html, status_code=status.HTTP_400_BAD_REQUEST)

    redirect_dest = auth_config.frontend_url or "https://app.limo-ai.online"

    session_cookie_kwargs = {
        "httponly": True,
        "samesite": "lax",
        "max_age": 60 * 60 * 24 * auth_config.session_expiry_days,
        "secure": auth_config.is_web_surface,
    }
    if auth_config.cookie_domain:
        session_cookie_kwargs["domain"] = auth_config.cookie_domain

    user_dict = {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "provider": user.provider,
        "created_at": user.created_at.isoformat() if hasattr(user.created_at, "isoformat") else str(user.created_at),
    }

    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <title>Limo Authentication</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      display: flex;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      background: #0f1117;
      color: #e2e8f0;
    }}
    .box {{
      text-align: center;
      padding: 2rem;
    }}
    .spinner {{
      width: 36px;
      height: 36px;
      margin: 0 auto 1rem;
      border: 3px solid rgba(255,255,255,0.1);
      border-top-color: #38bdf8;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }}
    @keyframes spin {{ to {{ transform: rotate(360deg); }} }}
  </style>
</head>
<body>
  <div class="box">
    <div class="spinner"></div>
    <h3 style="margin-bottom: 0.5rem;">Authentication Successful</h3>
    <p style="color: #94a3b8; font-size: 0.9rem;">Finalizing sign-in, closing window...</p>
  </div>
  <script>
    const authedUser = {json.dumps(user_dict)};
    if (window.opener) {{
      try {{
        window.opener.postMessage({{ type: 'LIMO_AUTH_SUCCESS', user: authedUser }}, '*');
      }} catch (err) {{
        console.error('postMessage error:', err);
      }}
      setTimeout(() => {{ window.close(); }}, 300);
    }} else {{
      window.location.href = "{redirect_dest}";
    }}
  </script>
</body>
</html>"""

    resp = HTMLResponse(content=html_content, status_code=status.HTTP_200_OK)
    resp.set_cookie(key="limo_session", value=session_token, **session_cookie_kwargs)
    del_kwargs = {"domain": auth_config.cookie_domain} if auth_config.cookie_domain else {}
    resp.delete_cookie("limo_oauth_state", **del_kwargs)
    resp.delete_cookie("oauth_state", **del_kwargs)
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

    del_kwargs = {"domain": auth_config.cookie_domain} if auth_config.cookie_domain else {}
    response.delete_cookie("limo_session", **del_kwargs)
    return {"status": "logged_out", "message": "Session invalidated successfully"}
