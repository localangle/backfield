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


class PaginatedClustersResponse(BaseModel):
    clusters: list[dict[str, Any]]
    total: int
    limit: int
    offset: int
    has_next: bool
    has_prev: bool


class PaginatedCandidatesResponse(BaseModel):
    candidates: list[dict[str, Any]]
    total: int
    has_next: bool
    has_prev: bool


@router.get("/candidates/clusters", response_model=PaginatedClustersResponse)
def candidates_clusters(
    project_slug: str = Query(...),
    status: str = Query("open"),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedClustersResponse:
    _ = status
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    return PaginatedClustersResponse(
        clusters=[],
        total=0,
        limit=limit,
        offset=offset,
        has_next=False,
        has_prev=False,
    )


@router.get("/candidates/ungrouped", response_model=PaginatedCandidatesResponse)
def candidates_ungrouped(
    project_slug: str = Query(...),
    status: str = Query("open"),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCandidatesResponse:
    _ = status
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    return PaginatedCandidatesResponse(candidates=[], total=0, has_next=False, has_prev=False)


@router.get("/candidates", response_model=PaginatedCandidatesResponse)
def candidates_list(
    project_slug: str = Query(...),
    status: str = Query("open"),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCandidatesResponse:
    _ = status
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    return PaginatedCandidatesResponse(candidates=[], total=0, has_next=False, has_prev=False)


@router.get("/candidates/types", response_model=dict[str, list[str]])
def candidates_types(
    project_slug: str = Query(...),
    status: str = Query("open"),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> dict[str, list[str]]:
    _ = status
    proj = _project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    return {"types": []}
