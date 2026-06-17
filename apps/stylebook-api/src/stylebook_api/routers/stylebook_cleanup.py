"""Stylebook cleanup checks — surface data-quality issues for human review."""

from __future__ import annotations

from typing import Any, Literal

from backfield_db import StylebookLocationCanonical
from backfield_entities.entities.location.merge import (
    canonical_has_linked_evidence,
    merge_location_canonical_into,
)
from backfield_entities.quality.checks import LOCATION_CLEANUP_CHECKS
from backfield_entities.quality.finders.duplicate_locations import (
    DEFAULT_FULL_SIMILARITY_THRESHOLD,
    DEFAULT_HEAD_SIMILARITY_THRESHOLD,
    cluster_display_label,
    count_duplicate_location_clusters,
    paginate_duplicate_location_clusters,
)
from backfield_entities.quality.finders.missing_geometry_locations import (
    count_missing_geometry_locations,
    list_missing_geometry_locations,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.canonical_evidence_counts import (
    linked_substrate_counts_by_location_canonical,
    mention_counts_by_location_canonical,
)
from stylebook_api.routers.stylebook_canonicals import CanonicalLocationResponse
from stylebook_api.semantic_reindex import enqueue_semantic_reindex_for_entity
from stylebook_api.stylebook_permissions import require_stylebook_edit_access
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
    label: str
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


class MergeCleanupCanonicalBody(BaseModel):
    target_canonical_id: str = Field(min_length=1)


class MergeCleanupCanonicalResponse(BaseModel):
    source_id: str
    target_id: str
    relinked_substrate_count: int
    source_deleted: bool


class DeleteCleanupCanonicalResponse(BaseModel):
    id: str
    message: str


def _count_for_check(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str,
    full_threshold: float,
    head_threshold: float,
) -> int:
    if check_id == "duplicate-locations":
        return count_duplicate_location_clusters(
            session,
            stylebook_id=stylebook_id,
            full_threshold=full_threshold,
            head_threshold=head_threshold,
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
        DEFAULT_FULL_SIMILARITY_THRESHOLD,
        ge=0.5,
        le=0.95,
        description="Minimum full-label trigram similarity for near-duplicate clusters.",
    ),
    head_similarity_threshold: float = Query(
        DEFAULT_HEAD_SIMILARITY_THRESHOLD,
        ge=0.5,
        le=0.95,
        description=(
            "Minimum similarity on the primary name (text before the first comma) "
            "to avoid suffix-only matches."
        ),
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
            full_threshold=similarity_threshold,
            head_threshold=head_similarity_threshold,
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
        DEFAULT_FULL_SIMILARITY_THRESHOLD,
        ge=0.5,
        le=0.95,
    ),
    head_similarity_threshold: float = Query(
        DEFAULT_HEAD_SIMILARITY_THRESHOLD,
        ge=0.5,
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
        full_threshold=similarity_threshold,
        head_threshold=head_similarity_threshold,
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
        cluster_label = cluster_display_label([canonical.label for canonical in canonicals])
        cluster_key = member_ids[0] if member_ids else str(index)
        clusters_out.append(
            DuplicateLocationClusterOut(
                cluster_id=f"{cluster_key}:{len(member_ids)}",
                label=cluster_label,
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


@router.post(
    "/{stylebook_slug}/cleanup/canonical-locations/{source_canonical_id}/merge-into",
    response_model=MergeCleanupCanonicalResponse,
)
def merge_cleanup_canonical_location(
    stylebook_slug: str,
    source_canonical_id: str,
    body: MergeCleanupCanonicalBody,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> MergeCleanupCanonicalResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    try:
        result = merge_location_canonical_into(
            session,
            stylebook_id=int(sb.id),
            organization_id=int(sb.organization_id),
            source_canonical_id=source_canonical_id,
            target_canonical_id=body.target_canonical_id,
        )
    except ValueError as exc:
        msg = str(exc)
        if "not in this stylebook" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc

    for project_id, location_id in result.relinked_substrates:
        enqueue_semantic_reindex_for_entity(
            session,
            project_id=project_id,
            entity_type="location",
            entity_id=location_id,
        )

    session.commit()
    return MergeCleanupCanonicalResponse(
        source_id=result.source_id,
        target_id=result.target_id,
        relinked_substrate_count=result.relinked_substrate_count,
        source_deleted=result.source_deleted,
    )


@router.delete(
    "/{stylebook_slug}/cleanup/canonical-locations/{canonical_id}",
    response_model=DeleteCleanupCanonicalResponse,
)
def delete_empty_cleanup_canonical_location(
    stylebook_slug: str,
    canonical_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> DeleteCleanupCanonicalResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical location not found")

    org_id = int(sb.organization_id)
    if canonical_has_linked_evidence(
        session,
        organization_id=org_id,
        canonical_id=str(canon.id),
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete a location that still has linked places. "
                "Merge it into another record first."
            ),
        )

    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=None,
        organization_id=org_id,
    )
    mention_count = mention_counts_by_location_canonical(
        session,
        project_ids=project_ids,
        canonical_ids=[str(canon.id)],
    ).get(str(canon.id), 0)
    if mention_count > 0:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a location that still has mentions.",
        )

    deleted_id = str(canon.id)
    session.delete(canon)
    session.commit()
    return DeleteCleanupCanonicalResponse(id=deleted_id, message="deleted")
