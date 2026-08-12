"""Stylebook UI dashboard stats."""

from __future__ import annotations

from typing import Any

from backfield_auth.gate import require_project_access
from backfield_db import (
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateLocation,
    SubstrateOrganization,
    SubstratePerson,
)
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING
from backfield_entities.catalog.resolve import resolve_stylebook_id_for_project_id
from backfield_entities.catalog.stylebook_library import resolve_stylebook_by_slug
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from stylebook_api.catalog_scope import StylebookSlugQuery
from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.project_scope import project_by_slug

router = APIRouter(prefix="/v1", tags=["stats"])


class StatsOut(BaseModel):
    locations: dict[str, int]
    people: dict[str, int]
    organizations: dict[str, int]
    works: dict[str, int]


def _zero_entity_stats() -> dict[str, int]:
    return {"canonical_count": 0, "candidate_count": 0}


def _resolve_stats_stylebook_id(
    session: Session,
    *,
    project_id: int,
    organization_id: int,
    stylebook_slug: str | None,
) -> int:
    """Catalog for home-card canonical counts.

    Path ``stylebook_slug`` wins when present (org-scoped). Otherwise use the
    project's assigned Stylebook. Pending candidates stay project-scoped and are
    only included when that project owns the same catalog.
    """
    raw = (stylebook_slug or "").strip()
    if raw:
        row = resolve_stylebook_by_slug(session, organization_id=organization_id, slug=raw)
        if row is None or row.id is None:
            raise HTTPException(
                status_code=404,
                detail="No catalog matches that name in your organization.",
            )
        return int(row.id)
    return resolve_stylebook_id_for_project_id(session, project_id)


@router.get("/stats", response_model=StatsOut)
def get_stats(
    project_slug: str = Query(...),
    stylebook_slug: StylebookSlugQuery = None,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> StatsOut:
    proj = project_by_slug(session, project_slug)
    require_project_access(session, auth, int(proj.id))
    project_id = int(proj.id)
    organization_id = int(proj.organization_id)

    auth_org = auth.get("organization_id")
    if auth_org is not None and int(auth_org) != organization_id:
        raise HTTPException(status_code=403, detail="Wrong organization")

    try:
        stylebook_id = _resolve_stats_stylebook_id(
            session,
            project_id=project_id,
            organization_id=organization_id,
            stylebook_slug=stylebook_slug,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    project_stylebook_id = resolve_stylebook_id_for_project_id(session, project_id)
    include_pending = project_stylebook_id == stylebook_id

    loc_canon = int(
        session.scalar(
            select(func.count())
            .select_from(StylebookLocationCanonical)
            .where(StylebookLocationCanonical.stylebook_id == stylebook_id)
        )
        or 0
    )
    people_canon = int(
        session.scalar(
            select(func.count())
            .select_from(StylebookPersonCanonical)
            .where(StylebookPersonCanonical.stylebook_id == stylebook_id)
        )
        or 0
    )
    org_canon = int(
        session.scalar(
            select(func.count())
            .select_from(StylebookOrganizationCanonical)
            .where(StylebookOrganizationCanonical.stylebook_id == stylebook_id)
        )
        or 0
    )

    loc_cand = 0
    people_cand = 0
    org_cand = 0
    if include_pending:
        loc_cand = int(
            session.scalar(
                select(func.count())
                .select_from(SubstrateLocation)
                .where(
                    SubstrateLocation.project_id == project_id,
                    col(SubstrateLocation.stylebook_location_canonical_id).is_(None),
                    SubstrateLocation.canonical_link_status == CANONICAL_LINK_PENDING,
                )
            )
            or 0
        )
        people_cand = int(
            session.scalar(
                select(func.count())
                .select_from(SubstratePerson)
                .where(
                    SubstratePerson.project_id == project_id,
                    col(SubstratePerson.stylebook_person_canonical_id).is_(None),
                    SubstratePerson.canonical_link_status == CANONICAL_LINK_PENDING,
                )
            )
            or 0
        )
        org_cand = int(
            session.scalar(
                select(func.count())
                .select_from(SubstrateOrganization)
                .where(
                    SubstrateOrganization.project_id == project_id,
                    col(SubstrateOrganization.stylebook_organization_canonical_id).is_(None),
                    SubstrateOrganization.canonical_link_status == CANONICAL_LINK_PENDING,
                )
            )
            or 0
        )

    return StatsOut(
        locations={"canonical_count": loc_canon, "candidate_count": loc_cand},
        people={"canonical_count": people_canon, "candidate_count": people_cand},
        organizations={"canonical_count": org_canon, "candidate_count": org_cand},
        works=_zero_entity_stats(),
    )
