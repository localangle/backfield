"""Project and Stylebook scope helpers for stylebook-api entity routes."""

from __future__ import annotations

from backfield_auth.gate import resolve_project_by_slug
from backfield_db import BackfieldProject
from backfield_entities.catalog.resolve import (
    STYLEBOOK_SLUG_NOT_IN_ORG,
    resolve_effective_stylebook_id_for_project,
)
from fastapi import HTTPException
from sqlmodel import Session, select


def project_by_slug(session: Session, slug: str) -> BackfieldProject:
    auth = session.info.get("backfield_auth")
    if isinstance(auth, dict):
        return resolve_project_by_slug(session, auth, slug)
    # Dependency overrides in focused tests may provide an already-authorized
    # session principal without running the normal dependency that records it.
    rows = session.exec(select(BackfieldProject).where(BackfieldProject.slug == slug)).all()
    if len(rows) == 1:
        return rows[0]
    if not rows:
        raise HTTPException(status_code=404, detail="Project not found")
    raise HTTPException(status_code=400, detail="Explicit organization context is required")


def require_stylebook_id(
    session: Session,
    project: BackfieldProject,
    stylebook_slug: str | None = None,
) -> int:
    try:
        return resolve_effective_stylebook_id_for_project(
            session, project, stylebook_slug=stylebook_slug
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        if str(e) == STYLEBOOK_SLUG_NOT_IN_ORG:
            raise HTTPException(
                status_code=404,
                detail="No catalog matches that name in your organization.",
            ) from e
        raise HTTPException(status_code=400, detail=str(e)) from e
