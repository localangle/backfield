"""Project and Stylebook scope helpers for stylebook-api entity routes."""

from __future__ import annotations

from backfield_db import BackfieldProject
from backfield_stylebook.resolve import (
    STYLEBOOK_SLUG_NOT_IN_ORG,
    resolve_effective_stylebook_id_for_project,
)
from fastapi import HTTPException
from sqlmodel import Session, select


def project_by_slug(session: Session, slug: str) -> BackfieldProject:
    row = session.exec(select(BackfieldProject).where(BackfieldProject.slug == slug)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return row


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
