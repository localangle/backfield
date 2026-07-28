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
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from stylebook_api.catalog_scope import StylebookSlugQuery
from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.project_scope import project_by_slug, require_stylebook_id

router = APIRouter(prefix="/v1", tags=["stats"])


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
    org_canon_cnt = int(
        session.scalar(
            select(func.count())
            .select_from(StylebookOrganizationCanonical)
            .where(StylebookOrganizationCanonical.stylebook_id == int(stylebook_id))
        )
        or 0
    )
    org_cand_cnt = int(
        session.scalar(
            select(func.count())
            .select_from(SubstrateOrganization)
            .where(
                SubstrateOrganization.project_id == int(proj.id),
                col(SubstrateOrganization.stylebook_organization_canonical_id).is_(None),
                SubstrateOrganization.canonical_link_status == CANONICAL_LINK_PENDING,
            )
        )
        or 0
    )
    org_stats = {
        "canonical_count": org_canon_cnt,
        "candidate_count": org_cand_cnt,
    }
    return StatsOut(locations=loc, people=people_stats, organizations=org_stats, works=z)
