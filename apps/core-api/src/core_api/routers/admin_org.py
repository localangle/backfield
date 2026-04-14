"""Org admin: users in an organization."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganizationMembership,
    BackfieldUser,
)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from core_api.authz import require_org_admin
from core_api.deps import get_auth, get_session
from core_api.security import hash_password

router = APIRouter(prefix="/organizations", tags=["admin"])


class UserCreateBody(BaseModel):
    email: str
    password: str
    display_name: str | None = None
    role: str = "member"


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str | None
    role: str


@router.get("/{org_id}/users", response_model=list[UserOut])
def list_users(
    org_id: int,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
):
    require_org_admin(session, auth, org_id)
    memberships = session.exec(
        select(BackfieldOrganizationMembership).where(
            BackfieldOrganizationMembership.organization_id == org_id
        )
    ).all()
    out: list[UserOut] = []
    for m in memberships:
        u = session.get(BackfieldUser, m.user_id)
        if u is None:
            continue
        out.append(
            UserOut(id=int(u.id), email=str(u.email), display_name=u.display_name, role=str(m.role))
        )
    return out


@router.post("/{org_id}/users", response_model=UserOut)
def create_user(
    org_id: int,
    body: UserCreateBody,
    session: Session = Depends(get_session),
    auth: dict = Depends(get_auth),
):
    require_org_admin(session, auth, org_id)
    email = body.email.strip().lower()
    existing = session.exec(select(BackfieldUser).where(BackfieldUser.email == email)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    user = BackfieldUser(
        email=email,
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    )
    session.add(user)
    session.flush()
    session.add(
        BackfieldOrganizationMembership(
            user_id=int(user.id),
            organization_id=org_id,
            role=body.role if body.role in ("org_admin", "member") else "member",
        )
    )
    session.commit()
    session.refresh(user)
    mem = session.exec(
        select(BackfieldOrganizationMembership).where(
            BackfieldOrganizationMembership.user_id == user.id,
            BackfieldOrganizationMembership.organization_id == org_id,
        )
    ).first()
    role = str(mem.role) if mem else "member"
    return UserOut(
        id=int(user.id),
        email=str(user.email),
        display_name=user.display_name,
        role=role,
    )
