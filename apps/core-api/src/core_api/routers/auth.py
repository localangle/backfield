"""Login, logout, session — DB-backed users."""

from __future__ import annotations

import os

from backfield_auth import create_session_token, resolve_auth
from backfield_auth.deps import require_auth
from backfield_auth.identity import LoginCredentials, NewPasswordBody
from backfield_db import (
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldUser,
)
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ValidationError
from sqlmodel import Session, select

from core_api.authz import session_project_ids_for_user
from core_api.deps import get_auth, get_session
from core_api.security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class UserResponse(BaseModel):
    email: str
    authenticated: bool
    user_id: int | None = None
    organization_id: int | None = None
    organization_name: str | None = None
    org_role: str | None = None


class ChangePasswordBody(NewPasswordBody):
    pass


def _session_cookie_settings() -> dict[str, str | int | bool | None]:
    is_production = os.getenv("ENVIRONMENT") == "production"
    if is_production:
        domain = (os.getenv("SESSION_COOKIE_DOMAIN") or "").strip() or None
        return {
            "httponly": True,
            "secure": True,
            "samesite": "none",
            "path": "/",
            "domain": domain,
            "max_age": 7 * 24 * 60 * 60,
        }
    return {
        "httponly": True,
        "secure": False,
        "samesite": "lax",
        "path": "/",
        "domain": None,
        "max_age": 7 * 24 * 60 * 60,
    }


def _set_session_cookie(response: Response, token: str) -> None:
    settings = _session_cookie_settings()
    response.set_cookie(key="session", value=token, **settings)


def _clear_session_cookie(response: Response) -> None:
    settings = _session_cookie_settings()
    response.delete_cookie(
        key="session",
        path=str(settings["path"]),
        domain=settings["domain"],  # type: ignore[arg-type]
        secure=bool(settings["secure"]),
        samesite=str(settings["samesite"]),  # type: ignore[arg-type]
    )


@router.post("/login")
def login(
    body: LoginCredentials,
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, bool | str]:
    email_norm = body.email
    user = session.exec(select(BackfieldUser).where(BackfieldUser.email == email_norm)).first()
    if user is None or user.disabled_at is not None:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    mem = session.exec(
        select(BackfieldOrganizationMembership).where(
            BackfieldOrganizationMembership.user_id == user.id
        )
    ).first()
    if mem is None:
        raise HTTPException(status_code=403, detail="User has no organization membership")

    org_id = int(mem.organization_id)
    org_role = str(mem.role)
    project_ids = session_project_ids_for_user(
        session,
        user_id=int(user.id),
        organization_id=org_id,
        org_role=org_role,
    )
    is_admin = org_role == "org_admin"

    token = create_session_token(
        user_id=int(user.id),
        email=str(user.email),
        projects=project_ids,
        organization_id=org_id,
        org_role=org_role,
        is_admin=is_admin,
    )
    _set_session_cookie(response, token)
    return {"success": True, "email": str(user.email)}


@router.get("/me", response_model=UserResponse)
def me(
    session: Session = Depends(get_session),
    cookie: str | None = Cookie(None, alias="session"),
    authorization: str | None = Header(None, alias="Authorization"),
) -> UserResponse:
    if not cookie and not authorization:
        return UserResponse(email="", authenticated=False)
    try:
        auth = resolve_auth(session, cookie=cookie, authorization=authorization)
    except HTTPException:
        return UserResponse(email="", authenticated=False)
    if auth.get("type") != "session":
        return UserResponse(email="", authenticated=False)
    user = auth["user"]
    org_id = int(auth["organization_id"])
    org = session.get(BackfieldOrganization, org_id)
    return UserResponse(
        email=str(user.email),
        authenticated=True,
        user_id=int(user.id),
        organization_id=org_id,
        organization_name=str(org.name) if org is not None else None,
        org_role=str(auth.get("org_role")),
    )


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
) -> dict[str, bool]:
    if auth["type"] != "session":
        raise HTTPException(status_code=403, detail="Session required")
    user = auth["user"]
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=401, detail="Current password is incorrect")
    try:
        new_password = body.validated_new_password(email=str(user.email))
    except (ValidationError, ValueError) as exc:
        detail = exc.errors()[0]["msg"] if isinstance(exc, ValidationError) else str(exc)
        raise HTTPException(status_code=400, detail=detail) from exc
    user.password_hash = hash_password(new_password)
    session.add(user)
    session.commit()
    return {"ok": True}


@router.post("/logout")
def logout(response: Response) -> dict[str, bool | str]:
    _clear_session_cookie(response)
    return {"success": True, "message": "Logged out successfully"}


@router.get("/session-check")
def session_check(username: str = Depends(require_auth)) -> dict[str, str]:
    return {"username": username}
