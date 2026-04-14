"""Create the first org admin when no users exist (HTTP bootstrap or env bootstrap)."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldProject,
    BackfieldProjectMembership,
    BackfieldUser,
)
from sqlmodel import Session, select

from core_api.security import hash_password

DEFAULT_ORG_SLUG = "default"


class BootstrapOrgMissingError(Exception):
    """Raised when the default organization row is missing (migrations not applied)."""


def ensure_first_org_admin(
    session: Session,
    email: str,
    password: str,
    display_name: str | None = None,
) -> dict[str, str | int | bool] | None:
    """Create first user and memberships, or return None if users already exist."""
    if session.exec(select(BackfieldUser).limit(1)).first() is not None:
        return None

    org = session.exec(
        select(BackfieldOrganization).where(BackfieldOrganization.slug == DEFAULT_ORG_SLUG)
    ).first()
    if org is None:
        raise BootstrapOrgMissingError("Default organization missing; run migrations")

    user = BackfieldUser(
        email=email.strip().lower(),
        password_hash=hash_password(password),
        display_name=display_name,
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
