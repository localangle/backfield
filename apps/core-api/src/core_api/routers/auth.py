"""Login, logout, session — DB-backed users."""

from __future__ import annotations

import os

from backfield_auth import create_session_token, verify_session_token
from backfield_auth.deps import require_auth
from backfield_db import (
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldUser,
)
from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlmodel import Session, select

from core_api.authz import session_project_ids_for_user
from core_api.deps import get_auth, get_session
from core_api.security import hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    email: str
    authenticated: bool
    user_id: int | None = None
    organization_id: int | None = None
    organization_name: str | None = None
    org_role: str | None = None


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str


def _set_session_cookie(response: Response, token: str) -> None:
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
        value=token,
        httponly=True,
        secure=secure_setting,
        samesite=samesite_setting,
        path="/",
        domain=cookie_domain,
        max_age=7 * 24 * 60 * 60,
    )


@router.post("/login")
def login(
    body: LoginRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> dict[str, bool | str]:
    email_norm = body.email.strip().lower()
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
def me(session: Session = Depends(get_session), cookie: str | None = Cookie(None, alias="session")):
    if not cookie:
        return UserResponse(email="", authenticated=False)
    data = verify_session_token(cookie)
    if not data:
        return UserResponse(email="", authenticated=False)
    uid = data.get("user_id")
    if uid is None:
        return UserResponse(email="", authenticated=False)
    user = session.get(BackfieldUser, int(uid))
    if user is None or user.disabled_at is not None:
        return UserResponse(email="", authenticated=False)
    org_id = data.get("organization_id")
    org_name: str | None = None
    if org_id is not None:
        org = session.get(BackfieldOrganization, int(org_id))
        if org is not None:
            org_name = str(org.name)
    return UserResponse(
        email=str(user.email),
        authenticated=True,
        user_id=int(user.id),
        organization_id=org_id,
        organization_name=org_name,
        org_role=data.get("org_role"),
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
    if len(body.new_password) < 1:
        raise HTTPException(status_code=400, detail="New password is required")
    user.password_hash = hash_password(body.new_password)
    session.add(user)
    session.commit()
    return {"ok": True}


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
    return {"username": username}
