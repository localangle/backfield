"""One-time bootstrap when no users exist."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldProject,
    BackfieldProjectMembership,
    BackfieldUser,
)
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from core_api.deps import get_session
from core_api.security import hash_password

router = APIRouter(prefix="/bootstrap", tags=["bootstrap"])


class FirstUserBody(BaseModel):
    email: str
    password: str
    display_name: str | None = None


@router.post("/first-user")
def register_first_user(
    body: FirstUserBody, session: Session = Depends(get_session)
) -> dict[str, str | int | bool]:
    if session.exec(select(BackfieldUser).limit(1)).first() is not None:
        raise HTTPException(status_code=400, detail="Users already exist; bootstrap disabled")

    org = session.exec(
        select(BackfieldOrganization).where(BackfieldOrganization.slug == "default")
    ).first()
    if org is None:
        raise HTTPException(status_code=500, detail="Default organization missing; run migrations")

    user = BackfieldUser(
        email=body.email.strip().lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    )
    session.add(user)
    session.flush()

    session.add(
        BackfieldOrganizationMembership(
            user_id=int(user.id),
            organization_id=int(org.id),
            role="org_admin",
        )
    )

    projects = session.exec(
        select(BackfieldProject).where(BackfieldProject.organization_id == org.id)
    ).all()
    for p in projects:
        session.add(
            BackfieldProjectMembership(
                user_id=int(user.id),
                project_id=int(p.id),
                role="member",
            )
        )

    session.commit()
    return {"ok": True, "user_id": int(user.id), "organization_id": int(org.id)}
