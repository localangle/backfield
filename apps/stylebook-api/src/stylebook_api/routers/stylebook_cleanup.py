"""Stylebook cleanup checks — surface data-quality issues for human review."""

from __future__ import annotations

from typing import Any, Literal

from backfield_db import StylebookLocationCanonical
from backfield_entities.quality.checks import LOCATION_CLEANUP_CHECKS
from backfield_entities.quality.finders.duplicate_locations import (
    DEFAULT_DUPLICATE_SIMILARITY_THRESHOLD,
    count_duplicate_location_clusters,
    paginate_duplicate_location_clusters,
)
from backfield_entities.quality.finders.missing_geometry_locations import (
    count_missing_geometry_locations,
    list_missing_geometry_locations,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import Session

from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.canonical_evidence_counts import (
    linked_substrate_counts_by_location_canonical,
    mention_counts_by_location_canonical,
)
from stylebook_api.routers.stylebook_canonicals import CanonicalLocationResponse
from stylebook_api.stylebook_scope import (
    optional_project_filter_to_ids,
    require_stylebook_by_slug_in_auth_org,
)

router = APIRouter(prefix="/v1/stylebooks", tags=["stylebook-cleanup"])


class CleanupCheckOut(BaseModel):
    id: str
    title: str
    description: str
    entity_type: str
    kind: Literal["cluster", "list"]
    count: int = 0


class CleanupChecksResponse(BaseModel):
    checks: list[CleanupCheckOut]
    total_open: int = 0


class DuplicateLocationClusterOut(BaseModel):
    cluster_id: str
    canonicals: list[CanonicalLocationResponse]


class PaginatedDuplicateClustersResponse(BaseModel):
    clusters: list[DuplicateLocationClusterOut]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class PaginatedCleanupLocationsResponse(BaseModel):
    canonicals: list[CanonicalLocationResponse]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


def _count_for_check(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str,
    similarity_threshold: float,
) -> int:
    if check_id == "duplicate-locations":
        return count_duplicate_location_clusters(
            session,
            stylebook_id=stylebook_id,
            threshold=similarity_threshold,
        )
    if check_id == "missing-geometry-locations":
        return count_missing_geometry_locations(session, stylebook_id=stylebook_id)
    return 0


def _canonical_responses_with_counts(
    session: Session,
    *,
    project_ids: list[int],
    rows_by_id: dict[str, Any],
    canonical_ids: list[str],
) -> list[CanonicalLocationResponse]:
    mc = mention_counts_by_location_canonical(
        session, project_ids=project_ids, canonical_ids=canonical_ids
    )
    lc = linked_substrate_counts_by_location_canonical(
        session, project_ids=project_ids, canonical_ids=canonical_ids
    )
    out: list[CanonicalLocationResponse] = []
    for cid in canonical_ids:
        row = rows_by_id.get(cid)
        if row is None:
            continue
        out.append(
            CanonicalLocationResponse.from_row(
                row,
                linked_substrate_count=lc.get(cid, 0),
                mention_count=mc.get(cid, 0),
            )
        )
    return out


@router.get("/{stylebook_slug}/cleanup/checks", response_model=CleanupChecksResponse)
def list_cleanup_checks(
    stylebook_slug: str,
    similarity_threshold: float = Query(
        DEFAULT_DUPLICATE_SIMILARITY_THRESHOLD,
        ge=0.3,
        le=0.95,
        description="Minimum trigram similarity for duplicate-location clusters.",
    ),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupChecksResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    stylebook_id = int(sb.id)
    checks_out: list[CleanupCheckOut] = []
    total_open = 0
    for check in LOCATION_CLEANUP_CHECKS:
        count = _count_for_check(
            session,
            stylebook_id=stylebook_id,
            check_id=check.id,
            similarity_threshold=similarity_threshold,
        )
        total_open += count
        checks_out.append(
            CleanupCheckOut(
                id=check.id,
                title=check.title,
                description=check.description,
                entity_type=check.entity_type,
                kind=check.kind,
                count=count,
            )
        )
    return CleanupChecksResponse(checks=checks_out, total_open=total_open)


@router.get(
    "/{stylebook_slug}/cleanup/checks/duplicate-locations",
    response_model=PaginatedDuplicateClustersResponse,
)
def list_duplicate_location_clusters(
    stylebook_slug: str,
    project: str | None = Query(
        None,
        description="Optional project slug to scope linked/mention counts.",
    ),
    similarity_threshold: float = Query(
        DEFAULT_DUPLICATE_SIMILARITY_THRESHOLD,
        ge=0.3,
        le=0.95,
    ),
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedDuplicateClustersResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )
    stylebook_id = int(sb.id)
    cluster_id_lists, total = paginate_duplicate_location_clusters(
        session,
        stylebook_id=stylebook_id,
        threshold=similarity_threshold,
        limit=limit,
        offset=offset,
    )
    all_ids = sorted({cid for cluster in cluster_id_lists for cid in cluster})
    rows_by_id = {
        cid: session.get(StylebookLocationCanonical, cid)
        for cid in all_ids
        if session.get(StylebookLocationCanonical, cid) is not None
    }
    clusters_out: list[DuplicateLocationClusterOut] = []
    for index, member_ids in enumerate(cluster_id_lists):
        canonicals = _canonical_responses_with_counts(
            session,
            project_ids=project_ids,
            rows_by_id=rows_by_id,
            canonical_ids=member_ids,
        )
        cluster_key = member_ids[0] if member_ids else str(index)
        clusters_out.append(
            DuplicateLocationClusterOut(
                cluster_id=f"{cluster_key}:{len(member_ids)}",
                canonicals=canonicals,
            )
        )
    page = offset // limit + 1 if limit else 1
    return PaginatedDuplicateClustersResponse(
        clusters=clusters_out,
        total=total,
        page=page,
        per_page=limit,
        has_next=offset + len(clusters_out) < total,
        has_prev=offset > 0,
    )


@router.get(
    "/{stylebook_slug}/cleanup/checks/missing-geometry-locations",
    response_model=PaginatedCleanupLocationsResponse,
)
def list_missing_geometry_location_check(
    stylebook_slug: str,
    project: str | None = Query(
        None,
        description="Optional project slug to scope linked/mention counts.",
    ),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCleanupLocationsResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=int(sb.organization_id),
    )
    stylebook_id = int(sb.id)
    items, total = list_missing_geometry_locations(
        session,
        stylebook_id=stylebook_id,
        limit=limit,
        offset=offset,
    )
    cids = [item.id for item in items]
    rows_by_id = {
        cid: session.get(StylebookLocationCanonical, cid)
        for cid in cids
        if session.get(StylebookLocationCanonical, cid) is not None
    }
    canonicals = _canonical_responses_with_counts(
        session,
        project_ids=project_ids,
        rows_by_id=rows_by_id,
        canonical_ids=cids,
    )
    page = offset // limit + 1 if limit else 1
    return PaginatedCleanupLocationsResponse(
        canonicals=canonicals,
        total=total,
        page=page,
        per_page=limit,
        has_next=offset + len(canonicals) < total,
        has_prev=offset > 0,
    )
