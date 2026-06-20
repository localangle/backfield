"""Stylebook cleanup checks — surface data-quality issues for human review."""

from __future__ import annotations

from typing import Any, Literal

from backfield_db import (
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from backfield_entities.entities.location.merge import (
    canonical_has_linked_evidence as location_has_linked_evidence,
)
from backfield_entities.entities.location.merge import (
    merge_location_canonical_into,
)
from backfield_entities.entities.organization.merge import (
    canonical_has_linked_evidence as organization_has_linked_evidence,
)
from backfield_entities.entities.organization.merge import (
    merge_organization_canonical_into,
)
from backfield_entities.entities.person.merge import (
    canonical_has_linked_evidence as person_has_linked_evidence,
)
from backfield_entities.entities.person.merge import (
    merge_person_canonical_into,
)
from backfield_entities.quality.checks import STYLEBOOK_CLEANUP_CHECKS, cleanup_check_by_id
from backfield_entities.quality.dismissals import (
    dismiss_canonical_issue,
    dismiss_cluster_members,
)
from backfield_entities.quality.finders.duplicate_locations import (
    DEFAULT_FULL_SIMILARITY_THRESHOLD,
    DEFAULT_HEAD_SIMILARITY_THRESHOLD,
    count_duplicate_location_clusters,
    paginate_duplicate_location_clusters,
)
from backfield_entities.quality.finders.duplicate_locations import (
    cluster_display_label as location_cluster_display_label,
)
from backfield_entities.quality.finders.duplicate_organizations import (
    count_duplicate_organization_clusters,
    organization_cluster_display_label,
    paginate_duplicate_organization_clusters,
)
from backfield_entities.quality.finders.duplicate_people import (
    count_duplicate_person_clusters,
    paginate_duplicate_person_clusters,
    person_cluster_display_label,
)
from backfield_entities.quality.finders.location_geography_issues import (
    count_location_geography_issues,
    list_location_geography_issues,
)
from backfield_entities.quality.finders.location_name_mismatch import (
    count_location_name_mismatches,
    list_location_name_mismatches,
)
from backfield_entities.quality.finders.organization_name_mismatch import (
    count_organization_name_mismatches,
    list_organization_name_mismatches,
)
from backfield_entities.quality.finders.person_name_mismatch import (
    count_person_name_mismatches,
    list_person_name_mismatches,
)
from backfield_entities.quality.types import (
    CleanupLocationGeographyIssueRow,
    CleanupNameMismatchIssueRow,
)
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlmodel import Session

from stylebook_api.deps import get_auth, get_session
from stylebook_api.helpers.canonical_evidence_counts import (
    linked_substrate_counts_by_location_canonical,
    linked_substrate_counts_by_organization_canonical,
    linked_substrate_counts_by_person_canonical,
    mention_counts_by_location_canonical,
    mention_counts_by_organization_canonical,
    mention_counts_by_person_canonical,
)
from stylebook_api.routers.stylebook_canonicals import CanonicalLocationResponse
from stylebook_api.routers.stylebook_organization_canonicals import CanonicalOrganizationResponse
from stylebook_api.routers.stylebook_person_canonicals import CanonicalPersonResponse
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


class DuplicatePersonClusterOut(BaseModel):
    cluster_id: str
    label: str
    canonicals: list[CanonicalPersonResponse]


class DuplicateOrganizationClusterOut(BaseModel):
    cluster_id: str
    label: str
    canonicals: list[CanonicalOrganizationResponse]


class CleanupLocationIssueOut(CanonicalLocationResponse):
    geography_issue: Literal["missing_geometry", "distant_linked_places"]
    distant_linked_count: int = 0


class PaginatedDuplicateClustersResponse(BaseModel):
    clusters: list[
        DuplicateLocationClusterOut
        | DuplicatePersonClusterOut
        | DuplicateOrganizationClusterOut
    ]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class PaginatedCleanupLocationsResponse(BaseModel):
    canonicals: list[CleanupLocationIssueOut]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class CleanupPersonMismatchIssueOut(CanonicalPersonResponse):
    mismatched_linked_count: int = 0
    mismatched_examples: list[str] = Field(default_factory=list)


class CleanupOrganizationMismatchIssueOut(CanonicalOrganizationResponse):
    mismatched_linked_count: int = 0
    mismatched_examples: list[str] = Field(default_factory=list)


class CleanupLocationMismatchIssueOut(CanonicalLocationResponse):
    mismatched_linked_count: int = 0
    mismatched_examples: list[str] = Field(default_factory=list)


class PaginatedCleanupPersonMismatchResponse(BaseModel):
    canonicals: list[CleanupPersonMismatchIssueOut]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class PaginatedCleanupOrganizationMismatchResponse(BaseModel):
    canonicals: list[CleanupOrganizationMismatchIssueOut]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class PaginatedCleanupLocationMismatchResponse(BaseModel):
    canonicals: list[CleanupLocationMismatchIssueOut]
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


class CreateCleanupDismissalBody(BaseModel):
    check_id: str = Field(min_length=1)
    member_ids: list[str] = Field(default_factory=list)
    canonical_id: str | None = None


class CleanupDismissalResponse(BaseModel):
    check_id: str
    dismissed_pair_count: int = 0
    dismissed_canonical_id: str | None = None
    message: str


def _created_by_user_id(auth: dict[str, Any]) -> int | None:
    if auth.get("type") != "session" or auth.get("user") is None:
        return None
    return int(auth["user"].id)  # type: ignore[union-attr]


def _count_for_check(
    session: Session,
    *,
    stylebook_id: int,
    organization_id: int,
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
    if check_id == "duplicate-people":
        return count_duplicate_person_clusters(
            session,
            stylebook_id=stylebook_id,
            full_threshold=full_threshold,
        )
    if check_id == "duplicate-organizations":
        return count_duplicate_organization_clusters(
            session,
            stylebook_id=stylebook_id,
            full_threshold=full_threshold,
        )
    if check_id == "missing-geometry-locations":
        return count_location_geography_issues(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
        )
    if check_id == "mismatched-people":
        return count_person_name_mismatches(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
        )
    if check_id == "mismatched-organizations":
        return count_organization_name_mismatches(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
        )
    if check_id == "mismatched-locations":
        return count_location_name_mismatches(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
        )
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


def _canonical_issue_responses_with_counts(
    session: Session,
    *,
    project_ids: list[int],
    rows_by_id: dict[str, StylebookLocationCanonical],
    items: list[CleanupLocationGeographyIssueRow],
) -> list[CleanupLocationIssueOut]:
    canonical_ids = [item.id for item in items]
    mc = mention_counts_by_location_canonical(
        session, project_ids=project_ids, canonical_ids=canonical_ids
    )
    lc = linked_substrate_counts_by_location_canonical(
        session, project_ids=project_ids, canonical_ids=canonical_ids
    )
    out: list[CleanupLocationIssueOut] = []
    for item in items:
        row = rows_by_id.get(item.id)
        if row is None:
            continue
        base = CanonicalLocationResponse.from_row(
            row,
            linked_substrate_count=lc.get(item.id, 0),
            mention_count=mc.get(item.id, 0),
        )
        out.append(
            CleanupLocationIssueOut(
                **base.model_dump(),
                geography_issue=item.issue,
                distant_linked_count=int(item.distant_linked_count),
            )
        )
    return out


def _person_responses_with_counts(
    session: Session,
    *,
    project_ids: list[int],
    rows_by_id: dict[str, StylebookPersonCanonical],
    canonical_ids: list[str],
) -> list[CanonicalPersonResponse]:
    mc = mention_counts_by_person_canonical(
        session, project_ids=project_ids, canonical_ids=canonical_ids
    )
    lc = linked_substrate_counts_by_person_canonical(
        session, project_ids=project_ids, canonical_ids=canonical_ids
    )
    out: list[CanonicalPersonResponse] = []
    for cid in canonical_ids:
        row = rows_by_id.get(cid)
        if row is None:
            continue
        out.append(
            CanonicalPersonResponse.from_canonical(
                row,
                linked_substrate_count=lc.get(cid, 0),
                mention_count=mc.get(cid, 0),
            )
        )
    return out


def _organization_responses_with_counts(
    session: Session,
    *,
    project_ids: list[int],
    rows_by_id: dict[str, StylebookOrganizationCanonical],
    canonical_ids: list[str],
) -> list[CanonicalOrganizationResponse]:
    mc = mention_counts_by_organization_canonical(
        session, project_ids=project_ids, canonical_ids=canonical_ids
    )
    lc = linked_substrate_counts_by_organization_canonical(
        session, project_ids=project_ids, canonical_ids=canonical_ids
    )
    out: list[CanonicalOrganizationResponse] = []
    for cid in canonical_ids:
        row = rows_by_id.get(cid)
        if row is None:
            continue
        out.append(
            CanonicalOrganizationResponse.from_canonical(
                row,
                linked_substrate_count=lc.get(cid, 0),
                mention_count=mc.get(cid, 0),
            )
        )
    return out


def _person_mismatch_responses_with_counts(
    session: Session,
    *,
    project_ids: list[int],
    rows_by_id: dict[str, StylebookPersonCanonical],
    items: list[CleanupNameMismatchIssueRow],
) -> list[CleanupPersonMismatchIssueOut]:
    canonical_ids = [item.id for item in items]
    base_rows = _person_responses_with_counts(
        session,
        project_ids=project_ids,
        rows_by_id=rows_by_id,
        canonical_ids=canonical_ids,
    )
    by_id = {row.id: row for row in base_rows}
    out: list[CleanupPersonMismatchIssueOut] = []
    for item in items:
        base = by_id.get(item.id)
        if base is None:
            continue
        out.append(
            CleanupPersonMismatchIssueOut(
                **base.model_dump(),
                mismatched_linked_count=int(item.mismatched_linked_count),
                mismatched_examples=list(item.mismatched_examples),
            )
        )
    return out


def _organization_mismatch_responses_with_counts(
    session: Session,
    *,
    project_ids: list[int],
    rows_by_id: dict[str, StylebookOrganizationCanonical],
    items: list[CleanupNameMismatchIssueRow],
) -> list[CleanupOrganizationMismatchIssueOut]:
    canonical_ids = [item.id for item in items]
    base_rows = _organization_responses_with_counts(
        session,
        project_ids=project_ids,
        rows_by_id=rows_by_id,
        canonical_ids=canonical_ids,
    )
    by_id = {row.id: row for row in base_rows}
    out: list[CleanupOrganizationMismatchIssueOut] = []
    for item in items:
        base = by_id.get(item.id)
        if base is None:
            continue
        out.append(
            CleanupOrganizationMismatchIssueOut(
                **base.model_dump(),
                mismatched_linked_count=int(item.mismatched_linked_count),
                mismatched_examples=list(item.mismatched_examples),
            )
        )
    return out


def _location_mismatch_responses_with_counts(
    session: Session,
    *,
    project_ids: list[int],
    rows_by_id: dict[str, StylebookLocationCanonical],
    items: list[CleanupNameMismatchIssueRow],
) -> list[CleanupLocationMismatchIssueOut]:
    canonical_ids = [item.id for item in items]
    base_rows = _canonical_responses_with_counts(
        session,
        project_ids=project_ids,
        rows_by_id=rows_by_id,
        canonical_ids=canonical_ids,
    )
    by_id = {row.id: row for row in base_rows}
    out: list[CleanupLocationMismatchIssueOut] = []
    for item in items:
        base = by_id.get(item.id)
        if base is None:
            continue
        out.append(
            CleanupLocationMismatchIssueOut(
                **base.model_dump(),
                mismatched_linked_count=int(item.mismatched_linked_count),
                mismatched_examples=list(item.mismatched_examples),
            )
        )
    return out


def _paginated_cluster_page(limit: int, offset: int) -> int:
    return offset // limit + 1 if limit else 1


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
    check_id: str | None = Query(
        None,
        description="When set, compute and return only this cleanup check.",
    ),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupChecksResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    stylebook_id = int(sb.id)
    organization_id = int(sb.organization_id)
    checks_to_list = STYLEBOOK_CLEANUP_CHECKS
    if check_id is not None:
        selected = cleanup_check_by_id(check_id.strip())
        if selected is None:
            raise HTTPException(status_code=404, detail=f"Unknown cleanup check: {check_id}")
        checks_to_list = (selected,)
    checks_out: list[CleanupCheckOut] = []
    total_open = 0
    for check in checks_to_list:
        count = _count_for_check(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
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
        cluster_label = location_cluster_display_label(
            [canonical.label for canonical in canonicals]
        )
        cluster_key = member_ids[0] if member_ids else str(index)
        clusters_out.append(
            DuplicateLocationClusterOut(
                cluster_id=f"{cluster_key}:{len(member_ids)}",
                label=cluster_label,
                canonicals=canonicals,
            )
        )
    page = _paginated_cluster_page(limit, offset)
    return PaginatedDuplicateClustersResponse(
        clusters=clusters_out,
        total=total,
        page=page,
        per_page=limit,
        has_next=offset + len(clusters_out) < total,
        has_prev=offset > 0,
    )


@router.get(
    "/{stylebook_slug}/cleanup/checks/duplicate-people",
    response_model=PaginatedDuplicateClustersResponse,
)
def list_duplicate_person_clusters(
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
    cluster_id_lists, total = paginate_duplicate_person_clusters(
        session,
        stylebook_id=stylebook_id,
        full_threshold=similarity_threshold,
        limit=limit,
        offset=offset,
    )
    all_ids = sorted({cid for cluster in cluster_id_lists for cid in cluster})
    rows_by_id = {
        cid: row
        for cid in all_ids
        if (row := session.get(StylebookPersonCanonical, cid)) is not None
    }
    clusters_out: list[DuplicatePersonClusterOut] = []
    for index, member_ids in enumerate(cluster_id_lists):
        canonicals = _person_responses_with_counts(
            session,
            project_ids=project_ids,
            rows_by_id=rows_by_id,
            canonical_ids=member_ids,
        )
        cluster_label = person_cluster_display_label([canonical.label for canonical in canonicals])
        cluster_key = member_ids[0] if member_ids else str(index)
        clusters_out.append(
            DuplicatePersonClusterOut(
                cluster_id=f"{cluster_key}:{len(member_ids)}",
                label=cluster_label,
                canonicals=canonicals,
            )
        )
    page = _paginated_cluster_page(limit, offset)
    return PaginatedDuplicateClustersResponse(
        clusters=clusters_out,
        total=total,
        page=page,
        per_page=limit,
        has_next=offset + len(clusters_out) < total,
        has_prev=offset > 0,
    )


@router.get(
    "/{stylebook_slug}/cleanup/checks/duplicate-organizations",
    response_model=PaginatedDuplicateClustersResponse,
)
def list_duplicate_organization_clusters(
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
    cluster_id_lists, total = paginate_duplicate_organization_clusters(
        session,
        stylebook_id=stylebook_id,
        full_threshold=similarity_threshold,
        limit=limit,
        offset=offset,
    )
    all_ids = sorted({cid for cluster in cluster_id_lists for cid in cluster})
    rows_by_id = {
        cid: row
        for cid in all_ids
        if (row := session.get(StylebookOrganizationCanonical, cid)) is not None
    }
    clusters_out: list[DuplicateOrganizationClusterOut] = []
    for index, member_ids in enumerate(cluster_id_lists):
        canonicals = _organization_responses_with_counts(
            session,
            project_ids=project_ids,
            rows_by_id=rows_by_id,
            canonical_ids=member_ids,
        )
        cluster_label = organization_cluster_display_label(
            [canonical.label for canonical in canonicals]
        )
        cluster_key = member_ids[0] if member_ids else str(index)
        clusters_out.append(
            DuplicateOrganizationClusterOut(
                cluster_id=f"{cluster_key}:{len(member_ids)}",
                label=cluster_label,
                canonicals=canonicals,
            )
        )
    page = _paginated_cluster_page(limit, offset)
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
    organization_id = int(sb.organization_id)
    items, total = list_location_geography_issues(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        project_ids=project_ids,
        limit=limit,
        offset=offset,
    )
    cids = [item.id for item in items]
    rows_by_id = {
        cid: row
        for cid in cids
        if (row := session.get(StylebookLocationCanonical, cid)) is not None
    }
    canonicals = _canonical_issue_responses_with_counts(
        session,
        project_ids=project_ids,
        rows_by_id=rows_by_id,
        items=items,
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


@router.get(
    "/{stylebook_slug}/cleanup/checks/mismatched-people",
    response_model=PaginatedCleanupPersonMismatchResponse,
)
def list_mismatched_people_check(
    stylebook_slug: str,
    project: str | None = Query(
        None,
        description="Optional project slug to scope linked/mention counts.",
    ),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCleanupPersonMismatchResponse:
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
    organization_id = int(sb.organization_id)
    items, total = list_person_name_mismatches(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        limit=limit,
        offset=offset,
    )
    cids = [item.id for item in items]
    rows_by_id = {
        cid: row
        for cid in cids
        if (row := session.get(StylebookPersonCanonical, cid)) is not None
    }
    canonicals = _person_mismatch_responses_with_counts(
        session,
        project_ids=project_ids,
        rows_by_id=rows_by_id,
        items=items,
    )
    page = offset // limit + 1 if limit else 1
    return PaginatedCleanupPersonMismatchResponse(
        canonicals=canonicals,
        total=total,
        page=page,
        per_page=limit,
        has_next=offset + len(canonicals) < total,
        has_prev=offset > 0,
    )


@router.get(
    "/{stylebook_slug}/cleanup/checks/mismatched-organizations",
    response_model=PaginatedCleanupOrganizationMismatchResponse,
)
def list_mismatched_organizations_check(
    stylebook_slug: str,
    project: str | None = Query(
        None,
        description="Optional project slug to scope linked/mention counts.",
    ),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCleanupOrganizationMismatchResponse:
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
    organization_id = int(sb.organization_id)
    items, total = list_organization_name_mismatches(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        limit=limit,
        offset=offset,
    )
    cids = [item.id for item in items]
    rows_by_id = {
        cid: row
        for cid in cids
        if (row := session.get(StylebookOrganizationCanonical, cid)) is not None
    }
    canonicals = _organization_mismatch_responses_with_counts(
        session,
        project_ids=project_ids,
        rows_by_id=rows_by_id,
        items=items,
    )
    page = offset // limit + 1 if limit else 1
    return PaginatedCleanupOrganizationMismatchResponse(
        canonicals=canonicals,
        total=total,
        page=page,
        per_page=limit,
        has_next=offset + len(canonicals) < total,
        has_prev=offset > 0,
    )


@router.get(
    "/{stylebook_slug}/cleanup/checks/mismatched-locations",
    response_model=PaginatedCleanupLocationMismatchResponse,
)
def list_mismatched_locations_check(
    stylebook_slug: str,
    project: str | None = Query(
        None,
        description="Optional project slug to scope linked/mention counts.",
    ),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCleanupLocationMismatchResponse:
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
    organization_id = int(sb.organization_id)
    items, total = list_location_name_mismatches(
        session,
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        limit=limit,
        offset=offset,
    )
    cids = [item.id for item in items]
    rows_by_id = {
        cid: row
        for cid in cids
        if (row := session.get(StylebookLocationCanonical, cid)) is not None
    }
    canonicals = _location_mismatch_responses_with_counts(
        session,
        project_ids=project_ids,
        rows_by_id=rows_by_id,
        items=items,
    )
    page = offset // limit + 1 if limit else 1
    return PaginatedCleanupLocationMismatchResponse(
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
    if location_has_linked_evidence(
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


@router.post(
    "/{stylebook_slug}/cleanup/canonical-people/{source_canonical_id}/merge-into",
    response_model=MergeCleanupCanonicalResponse,
)
def merge_cleanup_canonical_person(
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
        result = merge_person_canonical_into(
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

    for project_id, person_id in result.relinked_substrates:
        enqueue_semantic_reindex_for_entity(
            session,
            project_id=project_id,
            entity_type="person",
            entity_id=person_id,
        )

    session.commit()
    return MergeCleanupCanonicalResponse(
        source_id=result.source_id,
        target_id=result.target_id,
        relinked_substrate_count=result.relinked_substrate_count,
        source_deleted=result.source_deleted,
    )


@router.delete(
    "/{stylebook_slug}/cleanup/canonical-people/{canonical_id}",
    response_model=DeleteCleanupCanonicalResponse,
)
def delete_empty_cleanup_canonical_person(
    stylebook_slug: str,
    canonical_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> DeleteCleanupCanonicalResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookPersonCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical person not found")

    org_id = int(sb.organization_id)
    if person_has_linked_evidence(
        session,
        organization_id=org_id,
        canonical_id=str(canon.id),
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete a person that still has linked story people. "
                "Merge into another record first."
            ),
        )

    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=None,
        organization_id=org_id,
    )
    mention_count = mention_counts_by_person_canonical(
        session,
        project_ids=project_ids,
        canonical_ids=[str(canon.id)],
    ).get(str(canon.id), 0)
    if mention_count > 0:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a person that still has mentions.",
        )

    deleted_id = str(canon.id)
    session.delete(canon)
    session.commit()
    return DeleteCleanupCanonicalResponse(id=deleted_id, message="deleted")


@router.post(
    "/{stylebook_slug}/cleanup/canonical-organizations/{source_canonical_id}/merge-into",
    response_model=MergeCleanupCanonicalResponse,
)
def merge_cleanup_canonical_organization(
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
        result = merge_organization_canonical_into(
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

    for project_id, organization_id in result.relinked_substrates:
        enqueue_semantic_reindex_for_entity(
            session,
            project_id=project_id,
            entity_type="organization",
            entity_id=organization_id,
        )

    session.commit()
    return MergeCleanupCanonicalResponse(
        source_id=result.source_id,
        target_id=result.target_id,
        relinked_substrate_count=result.relinked_substrate_count,
        source_deleted=result.source_deleted,
    )


@router.delete(
    "/{stylebook_slug}/cleanup/canonical-organizations/{canonical_id}",
    response_model=DeleteCleanupCanonicalResponse,
)
def delete_empty_cleanup_canonical_organization(
    stylebook_slug: str,
    canonical_id: str,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> DeleteCleanupCanonicalResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    canon = session.get(StylebookOrganizationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(sb.id):
        raise HTTPException(status_code=404, detail="Canonical organization not found")

    org_id = int(sb.organization_id)
    if organization_has_linked_evidence(
        session,
        organization_id=org_id,
        canonical_id=str(canon.id),
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Cannot delete an organization that still has linked story records. "
                "Merge into another record first."
            ),
        )

    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=None,
        organization_id=org_id,
    )
    mention_count = mention_counts_by_organization_canonical(
        session,
        project_ids=project_ids,
        canonical_ids=[str(canon.id)],
    ).get(str(canon.id), 0)
    if mention_count > 0:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete an organization that still has mentions.",
        )

    deleted_id = str(canon.id)
    session.delete(canon)
    session.commit()
    return DeleteCleanupCanonicalResponse(id=deleted_id, message="deleted")


@router.post(
    "/{stylebook_slug}/cleanup/dismissals",
    response_model=CleanupDismissalResponse,
)
def create_cleanup_dismissal(
    stylebook_slug: str,
    body: CreateCleanupDismissalBody,
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupDismissalResponse:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    check = cleanup_check_by_id(body.check_id)
    if check is None:
        raise HTTPException(status_code=400, detail=f"Unknown cleanup check: {body.check_id}")

    stylebook_id = int(sb.id)
    user_id = _created_by_user_id(auth)
    if check.kind == "cluster":
        member_ids = sorted(
            {member_id.strip() for member_id in body.member_ids if member_id.strip()}
        )
        if len(member_ids) < 2:
            raise HTTPException(
                status_code=400,
                detail="member_ids must include at least two canonical ids for cluster checks",
            )
        inserted = dismiss_cluster_members(
            session,
            stylebook_id=stylebook_id,
            check_id=body.check_id,
            member_ids=member_ids,
            created_by_user_id=user_id,
        )
        session.commit()
        return CleanupDismissalResponse(
            check_id=body.check_id,
            dismissed_pair_count=inserted,
            message="Cluster marked as not a duplicate",
        )

    canonical_id = (body.canonical_id or "").strip()
    if not canonical_id:
        raise HTTPException(status_code=400, detail="canonical_id is required for list checks")
    dismiss_canonical_issue(
        session,
        stylebook_id=stylebook_id,
        check_id=body.check_id,
        canonical_id=canonical_id,
        created_by_user_id=user_id,
    )
    session.commit()
    return CleanupDismissalResponse(
        check_id=body.check_id,
        dismissed_canonical_id=canonical_id,
        message="Issue marked as reviewed",
    )
