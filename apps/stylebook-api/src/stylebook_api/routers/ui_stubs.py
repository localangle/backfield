"""Minimal HTTP responses for Stylebook UI routes not yet backed by substrate logic."""

from __future__ import annotations

from typing import Any

from backfield_auth.gate import require_project_access
from backfield_db import BackfieldProject
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, select

from stylebook_api.deps import get_auth, get_session

router = APIRouter(prefix="/v1", tags=["stylebook-ui-stubs"])


def _project_by_slug(session: Session, slug: str) -> BackfieldProject:
    row = session.exec(select(BackfieldProject).where(BackfieldProject.slug == slug)).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return row


class StatsOut(BaseModel):
    locations: dict[str, int]
    people: dict[str, int]
    organizations: dict[str, int]
    works: dict[str, int]


@router.get("/stats", response_model=StatsOut)
def get_stats(
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> StatsOut:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    z = {"canonical_count": 0, "candidate_count": 0}
    return StatsOut(locations=z, people=z, organizations=z, works=z)


@router.get("/agents/types", response_model=list[dict[str, Any]])
def agent_types(
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> list[dict[str, Any]]:
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    return []
