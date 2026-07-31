"""Stylebook-scoped helpers (org Stylebooks, optional project evidence filters)."""

from __future__ import annotations

from typing import Any

from backfield_auth.gate import require_project_access, visible_project_ids
from backfield_db import BackfieldProject, Stylebook
from backfield_entities.catalog.stylebook_library import resolve_stylebook_by_slug
from fastapi import HTTPException
from sqlmodel import Session, col, select


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
    stylebook_id: int | None = None,
) -> list[int]:
    """Return visible project ids assigned to one Stylebook."""

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
        if stylebook_id is not None and int(proj.stylebook_id) != stylebook_id:
            raise HTTPException(status_code=404, detail="Project not found")
        return [int(proj.id)]

    visible = visible_project_ids(session, auth)
    filters = [BackfieldProject.organization_id == organization_id]
    if stylebook_id is not None:
        filters.append(BackfieldProject.stylebook_id == stylebook_id)
    if visible is not None:
        filters.append(col(BackfieldProject.id).in_([int(pid) for pid in visible]))
    rows = session.exec(select(BackfieldProject.id).where(*filters)).all()
    return [int(r) for r in rows if r is not None]

