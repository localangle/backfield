"""
Dev-oriented session endpoints (env admin). Replaced by real user management later.

Mirrors agate-ai-platform auth-api login/me/logout enough to test cookies against Core API.
"""

from __future__ import annotations

import os

from backfield_auth import create_session_token, verify_session_token
from backfield_auth.deps import require_auth
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin")


class LoginRequest(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    username: str
    authenticated: bool


@router.post("/login")
def login(login_request: LoginRequest, response: Response) -> dict[str, bool | str]:
    """Set session cookie when credentials match env admin (until user tables exist)."""
    if login_request.username != ADMIN_USERNAME or login_request.password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    session_token = create_session_token(
        username=ADMIN_USERNAME,
        user_id=1,
        projects=[],
        is_admin=True,
    )

    is_production = os.getenv("ENVIRONMENT") == "production"
    if is_production:
        samesite_setting = "none"
        cookie_domain = os.getenv("SESSION_COOKIE_DOMAIN", ".example.invalid")
        secure_setting = True
    else:
        samesite_setting = "lax"
        cookie_domain = None
        secure_setting = False

    response.set_cookie(
        key="session",
        value=session_token,
        httponly=True,
        secure=secure_setting,
        samesite=samesite_setting,
        path="/",
        domain=cookie_domain,
        max_age=7 * 24 * 60 * 60,
    )
    return {"success": True, "username": ADMIN_USERNAME}


@router.get("/me", response_model=UserResponse)
def me(session: str | None = Cookie(None, alias="session")) -> UserResponse:
    if not session:
        return UserResponse(username="", authenticated=False)
    token_data = verify_session_token(session)
    if not token_data:
        return UserResponse(username="", authenticated=False)
    return UserResponse(username=str(token_data.get("username", "")), authenticated=True)


@router.post("/logout")
def logout(response: Response) -> dict[str, bool | str]:
    is_production = os.getenv("ENVIRONMENT") == "production"
    cookie_domain = os.getenv("SESSION_COOKIE_DOMAIN") if is_production else None
    secure_setting = bool(is_production)

    response.delete_cookie(
        key="session",
        path="/",
        domain=cookie_domain,
        secure=secure_setting,
        samesite="lax" if not is_production else "none",
    )
    return {"success": True, "message": "Logged out successfully"}


@router.get("/session-check")
def session_check(username: str = Depends(require_auth)) -> dict[str, str]:
    """Requires session cookie (not service token) — for integration tests."""
    return {"username": username}
