"""Minimal HTTP responses for Stylebook UI routes not yet backed by substrate logic."""

from __future__ import annotations

from typing import Any

from backfield_auth.gate import require_project_access
from backfield_db import (
    StylebookLocationCanonical,
    StylebookPersonCanonical,
    SubstrateLocation,
    SubstratePerson,
)
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session, col, func, select

from stylebook_api.catalog_scope import StylebookSlugQuery
from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.pagination import empty_page_metadata
from stylebook_api.helpers.project_scope import project_by_slug, require_stylebook_id

router = APIRouter(prefix="/v1", tags=["stylebook-ui-stubs"])


class StatsOut(BaseModel):
    locations: dict[str, int]
    people: dict[str, int]
    organizations: dict[str, int]
    works: dict[str, int]


@router.get("/stats", response_model=StatsOut)
def get_stats(
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> StatsOut:
    proj = project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    z = {"canonical_count": 0, "candidate_count": 0}
    try:
        stylebook_id = require_stylebook_id(session, proj, stylebook_slug)
    except HTTPException as e:
        if e.status_code == 400:
            return StatsOut(locations=z, people=z, organizations=z, works=z)
        raise e

    canon_cnt = int(
        session.scalar(
            select(func.count())
            .select_from(StylebookLocationCanonical)
            .where(StylebookLocationCanonical.stylebook_id == int(stylebook_id))
        )
        or 0
    )
    cand_cnt = int(
        session.scalar(
            select(func.count())
            .select_from(SubstrateLocation)
            .where(
                SubstrateLocation.project_id == int(proj.id),
                col(SubstrateLocation.stylebook_location_canonical_id).is_(None),
                SubstrateLocation.canonical_link_status == CANONICAL_LINK_PENDING,
            )
        )
        or 0
    )
    loc = {"canonical_count": canon_cnt, "candidate_count": cand_cnt}
    people_canon_cnt = int(
        session.scalar(
            select(func.count())
            .select_from(StylebookPersonCanonical)
            .where(StylebookPersonCanonical.stylebook_id == int(stylebook_id))
        )
        or 0
    )
    people_cand_cnt = int(
        session.scalar(
            select(func.count())
            .select_from(SubstratePerson)
            .where(
                SubstratePerson.project_id == int(proj.id),
                col(SubstratePerson.stylebook_person_canonical_id).is_(None),
                SubstratePerson.canonical_link_status == CANONICAL_LINK_PENDING,
            )
        )
        or 0
    )
    people_stats = {
        "canonical_count": people_canon_cnt,
        "candidate_count": people_cand_cnt,
    }
    return StatsOut(locations=loc, people=people_stats, organizations=z, works=z)


@router.get("/agents/types", response_model=list[dict[str, Any]])
def agent_types(
    project_slug: str = Query(...),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> list[dict[str, Any]]:
    proj = project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    return []


def _empty_page(*, limit: int, offset: int) -> tuple[int, int, bool, bool]:
    return empty_page_metadata(limit=limit, offset=offset)


class PaginatedOrganizationsStub(BaseModel):
    organizations: list[Any] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 25
    has_next: bool = False
    has_prev: bool = False


class PaginatedWorksStub(BaseModel):
    works: list[Any] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    per_page: int = 25
    has_next: bool = False
    has_prev: bool = False


# GET /v1/people removed — use GET /v1/canonical-people (entityListStubs updated separately).

@router.get("/organizations", response_model=PaginatedOrganizationsStub)
def list_organizations_stub(
    project_slug: str = Query(...),
    limit: int = Query(25, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedOrganizationsStub:
    proj = project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    page, _, has_next, has_prev = _empty_page(limit=limit, offset=offset)
    return PaginatedOrganizationsStub(
        page=page, per_page=limit, has_next=has_next, has_prev=has_prev
    )


@router.get("/works", response_model=PaginatedWorksStub)
def list_works_stub(
    project_slug: str = Query(...),
    limit: int = Query(25, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedWorksStub:
    proj = project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    page, _, has_next, has_prev = _empty_page(limit=limit, offset=offset)
    return PaginatedWorksStub(page=page, per_page=limit, has_next=has_next, has_prev=has_prev)
