"""Stylebook-scoped helpers (org Stylebooks, optional project evidence filters)."""

from __future__ import annotations

from typing import Any

from backfield_auth.gate import require_project_access, visible_project_ids
from backfield_db import BackfieldProject, Stylebook
from backfield_entities.stylebook_library import resolve_stylebook_by_slug
from fastapi import HTTPException
from sqlmodel import Session, select


def require_stylebook_by_slug_in_auth_org(
    session: Session,
    *,
    auth: dict[str, Any],
    stylebook_slug: str,
) -> Stylebook:
    """Resolve a Stylebook by slug inside the caller's organization.

    Service tokens do not carry an org id; we currently require a session or api key.
    """

    if auth.get("type") == "service":
        raise HTTPException(
            status_code=403,
            detail="Service tokens must use organization-scoped routes.",
        )

    org_id = int(auth["organization_id"])
    row = resolve_stylebook_by_slug(session, organization_id=org_id, slug=stylebook_slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    return row


def optional_project_filter_to_ids(
    session: Session,
    *,
    auth: dict[str, Any],
    project_slug: str | None,
    organization_id: int,
) -> list[int]:
    """Return project ids visible to the caller, optionally narrowed to one project slug."""

    if project_slug:
        proj = session.exec(
            select(BackfieldProject).where(
                BackfieldProject.slug == project_slug,
                BackfieldProject.organization_id == organization_id,
            )
        ).first()
        if proj is None or proj.id is None:
            raise HTTPException(status_code=404, detail="Project not found")
        require_project_access(session, auth, int(proj.id))
        return [int(proj.id)]

    visible = visible_project_ids(session, auth)
    if visible is None:
        rows = session.exec(
            select(BackfieldProject.id).where(BackfieldProject.organization_id == organization_id)
        ).all()
        return [int(r) for r in rows if r is not None]

    return [int(pid) for pid in visible]

