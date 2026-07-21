"""Stylebook cleanup checks — surface data-quality issues for human review."""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from backfield_db import (
    StylebookCleanupCheckRun,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from backfield_entities.activity import (
    EVENT_CLEANUP_DELETE,
    EVENT_CLEANUP_KEEP,
    EVENT_CLEANUP_KEEP_SEPARATE,
    EVENT_CLEANUP_MERGE,
    log_stylebook_activity_safe,
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
from backfield_entities.quality.check_runs import (
    CleanupRunScope,
    cleanup_algorithm_version,
    cleanup_scope_hash,
    count_visible_cached_results,
    get_active_cleanup_check_run,
    get_latest_cleanup_check_run,
    get_latest_succeeded_cleanup_check_run,
    query_cached_check_results,
    scope_to_json,
    validate_cleanup_check_id,
)
from backfield_entities.quality.checks import (
    STYLEBOOK_CLEANUP_CHECKS,
    CleanupCheckDef,
    cleanup_check_by_id,
)
from backfield_entities.quality.dismissals import (
    dismiss_canonical_issue,
    dismiss_cluster_members,
)
from backfield_entities.quality.finders.duplicate_locations import (
    DEFAULT_FULL_SIMILARITY_THRESHOLD,
    DEFAULT_HEAD_SIMILARITY_THRESHOLD,
)
from backfield_entities.quality.finders.duplicate_locations import (
    cluster_display_label as location_cluster_display_label,
)
from backfield_entities.quality.finders.duplicate_organizations import (
    organization_cluster_display_label,
)
from backfield_entities.quality.finders.duplicate_people import (
    person_cluster_display_label,
)
from backfield_entities.quality.types import (
    CleanupLocationGeographyIssueRow,
    CleanupNameMismatchIssueRow,
)
from celery import Celery
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

celery_app = Celery(
    "agate_worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)


def _celery_queue() -> str:
    return str(os.environ.get("CELERY_QUEUE", "agate"))


class CleanupCheckOut(BaseModel):
    id: str
    title: str
    description: str
    entity_type: str
    kind: Literal["cluster", "list"]
    count: int = 0
    status: str = "never_run"
    run_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    ran_at: datetime | None = None
    error_message: str | None = None


class CleanupCheckRunOut(BaseModel):
    id: str
    stylebook_id: int
    check_id: str
    status: str
    scope_hash: str
    candidate_count: int = 0
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    ran_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: StylebookCleanupCheckRun) -> CleanupCheckRunOut:
        return cls(
            id=str(row.id),
            stylebook_id=int(row.stylebook_id),
            check_id=str(row.check_id),
            status=str(row.status),
            scope_hash=str(row.scope_hash),
            candidate_count=int(row.candidate_count),
            error_message=row.error_message,
            started_at=row.started_at,
            completed_at=row.completed_at,
            ran_at=row.completed_at,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


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


class CleanupQuestionableOrganizationIssueOut(CanonicalOrganizationResponse):
    prefilter_score: int = 0
    prefilter_signals: list[str] = Field(default_factory=list)
    llm_decision: str = "flag"
    category: str = "other_non_organization"
    confidence: str = "medium"
    explanation: str = ""
    suggested_entity_type: str = "unknown"
    sample_mentions: list[str] = Field(default_factory=list)


class CleanupQuestionablePersonIssueOut(CanonicalPersonResponse):
    prefilter_score: int = 0
    prefilter_signals: list[str] = Field(default_factory=list)
    category: str = "organization_like"
    confidence: str = "medium"
    explanation: str = ""
    suggested_entity_type: str = "unknown"
    matching_organization_type: str | None = None
    sample_mentions: list[str] = Field(default_factory=list)


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


class PaginatedCleanupQuestionableOrganizationsResponse(BaseModel):
    canonicals: list[CleanupQuestionableOrganizationIssueOut]
    total: int
    page: int
    per_page: int
    has_next: bool
    has_prev: bool


class PaginatedCleanupQuestionablePeopleResponse(BaseModel):
    canonicals: list[CleanupQuestionablePersonIssueOut]
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


def _canonical_label_for_entity(
    session: Session,
    *,
    stylebook_id: int,
    entity_type: str,
    canonical_id: str,
) -> str | None:
    canonical_id = canonical_id.strip()
    if not canonical_id:
        return None
    if entity_type == "location":
        row = session.get(StylebookLocationCanonical, canonical_id)
    elif entity_type == "person":
        row = session.get(StylebookPersonCanonical, canonical_id)
    elif entity_type == "organization":
        row = session.get(StylebookOrganizationCanonical, canonical_id)
    else:
        return None
    if row is None or int(row.stylebook_id) != int(stylebook_id):
        return None
    return str(row.label).strip() or None


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


def _questionable_organization_responses_with_counts(
    session: Session,
    *,
    project_ids: list[int],
    rows_by_id: dict[str, StylebookOrganizationCanonical],
    cached_rows: list[Any],
) -> list[CleanupQuestionableOrganizationIssueOut]:
    canonical_ids = [
        str((row.canonical_ids_json or [None])[0])
        for row in cached_rows
        if row.canonical_ids_json
    ]
    base_rows = _organization_responses_with_counts(
        session,
        project_ids=project_ids,
        rows_by_id=rows_by_id,
        canonical_ids=canonical_ids,
    )
    by_id = {row.id: row for row in base_rows}
    out: list[CleanupQuestionableOrganizationIssueOut] = []
    for cached in cached_rows:
        canonical_ids_json = cached.canonical_ids_json or []
        if not canonical_ids_json:
            continue
        canonical_id = str(canonical_ids_json[0])
        base = by_id.get(canonical_id)
        if base is None:
            continue
        payload = cached.payload_json if isinstance(cached.payload_json, dict) else {}
        out.append(
            CleanupQuestionableOrganizationIssueOut(
                **base.model_dump(),
                prefilter_score=int(payload.get("prefilter_score", 0)),
                prefilter_signals=[
                    str(signal)
                    for signal in (payload.get("prefilter_signals") or [])
                    if str(signal).strip()
                ],
                llm_decision=str(payload.get("llm_decision") or "flag"),
                category=str(payload.get("category") or "other_non_organization"),
                confidence=str(payload.get("confidence") or "medium"),
                explanation=str(payload.get("explanation") or ""),
                suggested_entity_type=str(payload.get("suggested_entity_type") or "unknown"),
                sample_mentions=[
                    str(sample)
                    for sample in (payload.get("sample_mentions") or [])
                    if str(sample).strip()
                ],
            )
        )
    return out


def _questionable_person_responses_with_counts(
    session: Session,
    *,
    project_ids: list[int],
    rows_by_id: dict[str, StylebookPersonCanonical],
    cached_rows: list[Any],
) -> list[CleanupQuestionablePersonIssueOut]:
    canonical_ids = [
        str((row.canonical_ids_json or [None])[0])
        for row in cached_rows
        if row.canonical_ids_json
    ]
    base_rows = _person_responses_with_counts(
        session,
        project_ids=project_ids,
        rows_by_id=rows_by_id,
        canonical_ids=canonical_ids,
    )
    by_id = {row.id: row for row in base_rows}
    out: list[CleanupQuestionablePersonIssueOut] = []
    for cached in cached_rows:
        canonical_ids_json = cached.canonical_ids_json or []
        if not canonical_ids_json:
            continue
        canonical_id = str(canonical_ids_json[0])
        base = by_id.get(canonical_id)
        if base is None:
            continue
        payload = cached.payload_json if isinstance(cached.payload_json, dict) else {}
        out.append(
            CleanupQuestionablePersonIssueOut(
                **base.model_dump(),
                prefilter_score=int(payload.get("prefilter_score", 0)),
                prefilter_signals=[
                    str(signal)
                    for signal in (payload.get("prefilter_signals") or [])
                    if str(signal).strip()
                ],
                category=str(payload.get("category") or "organization_like"),
                confidence=str(payload.get("confidence") or "medium"),
                explanation=str(payload.get("explanation") or ""),
                suggested_entity_type=str(payload.get("suggested_entity_type") or "unknown"),
                matching_organization_type=(
                    str(payload.get("matching_organization_type"))
                    if payload.get("matching_organization_type")
                    else None
                ),
                sample_mentions=[
                    str(sample)
                    for sample in (payload.get("sample_mentions") or [])
                    if str(sample).strip()
                ],
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


def _cleanup_run_scope(
    *,
    stylebook_id: int,
    organization_id: int,
    check_id: str,
    project_ids: list[int],
    project_slug: str | None,
    full_threshold: float,
    head_threshold: float,
) -> CleanupRunScope:
    scoped_project_ids: tuple[int, ...] | None = None
    if project_slug:
        scoped_project_ids = tuple(sorted({int(project_id) for project_id in project_ids}))
    return CleanupRunScope(
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        check_id=check_id,
        full_threshold=full_threshold,
        head_threshold=head_threshold,
        project_ids=scoped_project_ids,
        project_slug=project_slug,
    )


def _visible_count_for_run(
    session: Session,
    *,
    run: StylebookCleanupCheckRun,
) -> int:
    return count_visible_cached_results(
        session,
        run_id=str(run.id),
        stylebook_id=int(run.stylebook_id),
        check_id=str(run.check_id),
    )


def _check_out_from_run(
    session: Session,
    *,
    check: CleanupCheckDef,
    latest_run: StylebookCleanupCheckRun | None,
    latest_succeeded: StylebookCleanupCheckRun | None = None,
) -> CleanupCheckOut:
    """Build a hub row from the latest run.

    When the latest run is still queued/running, preserve the last succeeded
    completion timestamp and open-item count so the hub does not flash
    "Not run yet" while a new pass is in flight.
    """
    if latest_run is None:
        return CleanupCheckOut(
            id=check.id,
            title=check.title,
            description=check.description,
            entity_type=check.entity_type,
            kind=check.kind,
            status="never_run",
        )
    count = 0
    completed_at = latest_run.completed_at
    if latest_run.status == "succeeded":
        count = _visible_count_for_run(session, run=latest_run)
    elif latest_run.status in ("queued", "running") and latest_succeeded is not None:
        count = _visible_count_for_run(session, run=latest_succeeded)
        completed_at = latest_succeeded.completed_at
    return CleanupCheckOut(
        id=check.id,
        title=check.title,
        description=check.description,
        entity_type=check.entity_type,
        kind=check.kind,
        count=count,
        status=str(latest_run.status),
        run_id=str(latest_run.id),
        started_at=latest_run.started_at,
        completed_at=completed_at,
        ran_at=completed_at,
        error_message=latest_run.error_message,
    )


def _empty_cluster_response(limit: int, offset: int) -> PaginatedDuplicateClustersResponse:
    page = _paginated_cluster_page(limit, offset)
    return PaginatedDuplicateClustersResponse(
        clusters=[],
        total=0,
        page=page,
        per_page=limit,
        has_next=False,
        has_prev=offset > 0,
    )


def _empty_location_issues_response(limit: int, offset: int) -> PaginatedCleanupLocationsResponse:
    page = offset // limit + 1 if limit else 1
    return PaginatedCleanupLocationsResponse(
        canonicals=[],
        total=0,
        page=page,
        per_page=limit,
        has_next=False,
        has_prev=offset > 0,
    )


def _empty_person_mismatch_response(
    limit: int,
    offset: int,
) -> PaginatedCleanupPersonMismatchResponse:
    page = offset // limit + 1 if limit else 1
    return PaginatedCleanupPersonMismatchResponse(
        canonicals=[],
        total=0,
        page=page,
        per_page=limit,
        has_next=False,
        has_prev=offset > 0,
    )


def _empty_organization_mismatch_response(
    limit: int,
    offset: int,
) -> PaginatedCleanupOrganizationMismatchResponse:
    page = offset // limit + 1 if limit else 1
    return PaginatedCleanupOrganizationMismatchResponse(
        canonicals=[],
        total=0,
        page=page,
        per_page=limit,
        has_next=False,
        has_prev=offset > 0,
    )


def _empty_questionable_organization_response(
    limit: int,
    offset: int,
) -> PaginatedCleanupQuestionableOrganizationsResponse:
    page = offset // limit + 1 if limit else 1
    return PaginatedCleanupQuestionableOrganizationsResponse(
        canonicals=[],
        total=0,
        page=page,
        per_page=limit,
        has_next=False,
        has_prev=offset > 0,
    )


def _empty_questionable_person_response(
    limit: int,
    offset: int,
) -> PaginatedCleanupQuestionablePeopleResponse:
    page = offset // limit + 1 if limit else 1
    return PaginatedCleanupQuestionablePeopleResponse(
        canonicals=[],
        total=0,
        page=page,
        per_page=limit,
        has_next=False,
        has_prev=offset > 0,
    )


def _empty_location_mismatch_response(
    limit: int,
    offset: int,
) -> PaginatedCleanupLocationMismatchResponse:
    page = offset // limit + 1 if limit else 1
    return PaginatedCleanupLocationMismatchResponse(
        canonicals=[],
        total=0,
        page=page,
        per_page=limit,
        has_next=False,
        has_prev=offset > 0,
    )


def _latest_succeeded_run_for_scope(
    session: Session,
    *,
    stylebook_id: int,
    check_id: str,
    scope: CleanupRunScope,
) -> StylebookCleanupCheckRun | None:
    scope_hash = cleanup_scope_hash(scope)
    return get_latest_succeeded_cleanup_check_run(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
        scope_hash=scope_hash,
    )


def _mismatch_items_from_cached_rows(
    session: Session,
    *,
    cached_rows: list[Any],
    entity_type: Literal["person", "organization", "location"],
) -> list[CleanupNameMismatchIssueRow]:
    items: list[CleanupNameMismatchIssueRow] = []
    for row in cached_rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        canonical_ids = row.canonical_ids_json or []
        if not canonical_ids:
            continue
        canonical_id = str(canonical_ids[0])
        if entity_type == "person":
            canon = session.get(StylebookPersonCanonical, canonical_id)
        elif entity_type == "organization":
            canon = session.get(StylebookOrganizationCanonical, canonical_id)
        else:
            canon = session.get(StylebookLocationCanonical, canonical_id)
        if canon is None:
            continue
        examples_raw = payload.get("mismatched_examples", [])
        if isinstance(examples_raw, list):
            examples = [str(example) for example in examples_raw]
        else:
            examples = []
        items.append(
            CleanupNameMismatchIssueRow(
                id=canonical_id,
                slug=str(canon.slug),
                label=str(row.label or canon.label),
                entity_type=entity_type,
                status=str(canon.status),
                mismatched_linked_count=int(payload.get("mismatched_linked_count", 0)),
                mismatched_examples=examples,
                location_type=getattr(canon, "location_type", None),
            )
        )
    return items


@router.get("/{stylebook_slug}/cleanup/checks", response_model=CleanupChecksResponse)
def list_cleanup_checks(
    stylebook_slug: str,
    project: str | None = Query(
        None,
        description="Optional project slug to scope list-style checks.",
    ),
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
        description="When set, return only this cleanup check.",
    ),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupChecksResponse:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    stylebook_id = int(sb.id)
    organization_id = int(sb.organization_id)
    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=organization_id,
    )
    checks_to_list = STYLEBOOK_CLEANUP_CHECKS
    if check_id is not None:
        selected = cleanup_check_by_id(check_id.strip())
        if selected is None:
            raise HTTPException(status_code=404, detail=f"Unknown cleanup check: {check_id}")
        checks_to_list = (selected,)
    checks_out: list[CleanupCheckOut] = []
    total_open = 0
    for check in checks_to_list:
        scope = _cleanup_run_scope(
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            check_id=check.id,
            project_ids=project_ids,
            project_slug=project,
            full_threshold=similarity_threshold,
            head_threshold=head_similarity_threshold,
        )
        scope_hash = cleanup_scope_hash(scope)
        latest_run = get_latest_cleanup_check_run(
            session,
            stylebook_id=stylebook_id,
            check_id=check.id,
            scope_hash=scope_hash,
        )
        latest_succeeded: StylebookCleanupCheckRun | None = None
        if latest_run is not None and latest_run.status in ("queued", "running"):
            latest_succeeded = get_latest_succeeded_cleanup_check_run(
                session,
                stylebook_id=stylebook_id,
                check_id=check.id,
                scope_hash=scope_hash,
            )
        check_out = _check_out_from_run(
            session,
            check=check,
            latest_run=latest_run,
            latest_succeeded=latest_succeeded,
        )
        total_open += check_out.count
        checks_out.append(check_out)
    return CleanupChecksResponse(checks=checks_out, total_open=total_open)


@router.post(
    "/{stylebook_slug}/cleanup/checks/{check_id}/runs",
    response_model=CleanupCheckRunOut,
)
def start_cleanup_check_run(
    stylebook_slug: str,
    check_id: str,
    project: str | None = Query(
        None,
        description="Optional project slug to scope list-style checks.",
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
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupCheckRunOut:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    try:
        normalized_check_id = validate_cleanup_check_id(check_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    stylebook_id = int(sb.id)
    organization_id = int(sb.organization_id)
    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=organization_id,
    )
    scope = _cleanup_run_scope(
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        check_id=normalized_check_id,
        project_ids=project_ids,
        project_slug=project,
        full_threshold=similarity_threshold,
        head_threshold=head_similarity_threshold,
    )
    scope_hash = cleanup_scope_hash(scope)
    active = get_active_cleanup_check_run(
        session,
        stylebook_id=stylebook_id,
        check_id=normalized_check_id,
        scope_hash=scope_hash,
    )
    if active is not None:
        return CleanupCheckRunOut.from_row(active)
    run = StylebookCleanupCheckRun(
        id=str(uuid.uuid4()),
        stylebook_id=stylebook_id,
        check_id=normalized_check_id,
        status="queued",
        scope_hash=scope_hash,
        scope_json=scope_to_json(scope),
        algorithm_version=cleanup_algorithm_version(normalized_check_id),
        created_by_user_id=_created_by_user_id(auth),
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    celery_app.send_task(
        "worker.tasks.execute_cleanup_check_run",
        args=[str(run.id)],
        queue=_celery_queue(),
    )
    return CleanupCheckRunOut.from_row(run)


@router.post(
    "/{stylebook_slug}/cleanup/checks/{check_id}/runs/cancel",
    response_model=CleanupCheckRunOut,
)
def cancel_cleanup_check_run_route(
    stylebook_slug: str,
    check_id: str,
    project: str | None = Query(
        None,
        description="Optional project slug to scope list-style checks.",
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
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupCheckRunOut:
    require_stylebook_edit_access(session, auth=auth, stylebook_slug=stylebook_slug)
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    try:
        normalized_check_id = validate_cleanup_check_id(check_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    stylebook_id = int(sb.id)
    organization_id = int(sb.organization_id)
    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=organization_id,
    )
    scope = _cleanup_run_scope(
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        check_id=normalized_check_id,
        project_ids=project_ids,
        project_slug=project,
        full_threshold=similarity_threshold,
        head_threshold=head_similarity_threshold,
    )
    scope_hash = cleanup_scope_hash(scope)
    active = get_active_cleanup_check_run(
        session,
        stylebook_id=stylebook_id,
        check_id=normalized_check_id,
        scope_hash=scope_hash,
    )
    if active is None:
        raise HTTPException(
            status_code=400,
            detail="No active check run to cancel.",
        )
    active.status = "cancelled"
    active.error_message = None
    active.completed_at = datetime.now(UTC)
    active.updated_at = datetime.now(UTC)
    session.add(active)
    session.commit()
    session.refresh(active)
    celery_app.control.revoke(str(active.id), terminate=True, signal="SIGTERM")
    return CleanupCheckRunOut.from_row(active)


@router.get(
    "/{stylebook_slug}/cleanup/checks/{check_id}/runs/latest",
    response_model=CleanupCheckRunOut | None,
)
def get_latest_cleanup_check_run_route(
    stylebook_slug: str,
    check_id: str,
    project: str | None = Query(
        None,
        description="Optional project slug to scope list-style checks.",
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
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> CleanupCheckRunOut | None:
    sb = require_stylebook_by_slug_in_auth_org(session, auth=auth, stylebook_slug=stylebook_slug)
    if sb.id is None:
        raise HTTPException(status_code=404, detail="Stylebook not found")
    try:
        normalized_check_id = validate_cleanup_check_id(check_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    stylebook_id = int(sb.id)
    organization_id = int(sb.organization_id)
    project_ids = optional_project_filter_to_ids(
        session,
        auth=auth,
        project_slug=project,
        organization_id=organization_id,
    )
    scope = _cleanup_run_scope(
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        check_id=normalized_check_id,
        project_ids=project_ids,
        project_slug=project,
        full_threshold=similarity_threshold,
        head_threshold=head_similarity_threshold,
    )
    scope_hash = cleanup_scope_hash(scope)
    latest = get_latest_cleanup_check_run(
        session,
        stylebook_id=stylebook_id,
        check_id=normalized_check_id,
        scope_hash=scope_hash,
    )
    if latest is None:
        return None
    return CleanupCheckRunOut.from_row(latest)


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
    q: str | None = Query(
        None,
        description="Optional label filter; returns clusters where any member label matches.",
    ),
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
    organization_id = int(sb.organization_id)
    check_id = "duplicate-locations"
    scope = _cleanup_run_scope(
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        check_id=check_id,
        project_ids=project_ids,
        project_slug=project,
        full_threshold=similarity_threshold,
        head_threshold=head_similarity_threshold,
    )
    run = _latest_succeeded_run_for_scope(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
        scope=scope,
    )
    if run is None:
        return _empty_cluster_response(limit, offset)
    cached_rows, total = query_cached_check_results(
        session,
        run_id=str(run.id),
        stylebook_id=stylebook_id,
        check_id=check_id,
        limit=limit,
        offset=offset,
        query=q,
    )
    all_ids = sorted({cid for row in cached_rows for cid in (row.canonical_ids_json or [])})
    rows_by_id = {
        cid: row
        for cid in all_ids
        if (row := session.get(StylebookLocationCanonical, cid)) is not None
    }
    clusters_out: list[DuplicateLocationClusterOut] = []
    for row in cached_rows:
        member_ids = [cid for cid in (row.canonical_ids_json or []) if cid in rows_by_id]
        if len(member_ids) < 2:
            continue
        canonicals = _canonical_responses_with_counts(
            session,
            project_ids=project_ids,
            rows_by_id=rows_by_id,
            canonical_ids=member_ids,
        )
        cluster_label = row.label or location_cluster_display_label(
            [canonical.label for canonical in canonicals]
        )
        clusters_out.append(
            DuplicateLocationClusterOut(
                cluster_id=row.item_key,
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
    q: str | None = Query(
        None,
        description="Optional label filter; returns clusters where any member label matches.",
    ),
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
    organization_id = int(sb.organization_id)
    check_id = "duplicate-people"
    scope = _cleanup_run_scope(
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        check_id=check_id,
        project_ids=project_ids,
        project_slug=project,
        full_threshold=similarity_threshold,
        head_threshold=DEFAULT_HEAD_SIMILARITY_THRESHOLD,
    )
    run = _latest_succeeded_run_for_scope(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
        scope=scope,
    )
    if run is None:
        return _empty_cluster_response(limit, offset)
    cached_rows, total = query_cached_check_results(
        session,
        run_id=str(run.id),
        stylebook_id=stylebook_id,
        check_id=check_id,
        limit=limit,
        offset=offset,
        query=q,
    )
    all_ids = sorted({cid for row in cached_rows for cid in (row.canonical_ids_json or [])})
    rows_by_id = {
        cid: row
        for cid in all_ids
        if (row := session.get(StylebookPersonCanonical, cid)) is not None
    }
    clusters_out: list[DuplicatePersonClusterOut] = []
    for row in cached_rows:
        member_ids = [cid for cid in (row.canonical_ids_json or []) if cid in rows_by_id]
        if len(member_ids) < 2:
            continue
        canonicals = _person_responses_with_counts(
            session,
            project_ids=project_ids,
            rows_by_id=rows_by_id,
            canonical_ids=member_ids,
        )
        cluster_label = row.label or person_cluster_display_label(
            [canonical.label for canonical in canonicals]
        )
        clusters_out.append(
            DuplicatePersonClusterOut(
                cluster_id=row.item_key,
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
    q: str | None = Query(
        None,
        description="Optional label filter; returns clusters where any member label matches.",
    ),
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
    organization_id = int(sb.organization_id)
    check_id = "duplicate-organizations"
    scope = _cleanup_run_scope(
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        check_id=check_id,
        project_ids=project_ids,
        project_slug=project,
        full_threshold=similarity_threshold,
        head_threshold=DEFAULT_HEAD_SIMILARITY_THRESHOLD,
    )
    run = _latest_succeeded_run_for_scope(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
        scope=scope,
    )
    if run is None:
        return _empty_cluster_response(limit, offset)
    cached_rows, total = query_cached_check_results(
        session,
        run_id=str(run.id),
        stylebook_id=stylebook_id,
        check_id=check_id,
        limit=limit,
        offset=offset,
        query=q,
    )
    all_ids = sorted({cid for row in cached_rows for cid in (row.canonical_ids_json or [])})
    rows_by_id = {
        cid: row
        for cid in all_ids
        if (row := session.get(StylebookOrganizationCanonical, cid)) is not None
    }
    clusters_out: list[DuplicateOrganizationClusterOut] = []
    for row in cached_rows:
        member_ids = [cid for cid in (row.canonical_ids_json or []) if cid in rows_by_id]
        if len(member_ids) < 2:
            continue
        canonicals = _organization_responses_with_counts(
            session,
            project_ids=project_ids,
            rows_by_id=rows_by_id,
            canonical_ids=member_ids,
        )
        cluster_label = row.label or organization_cluster_display_label(
            [canonical.label for canonical in canonicals]
        )
        clusters_out.append(
            DuplicateOrganizationClusterOut(
                cluster_id=row.item_key,
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
    check_id = "missing-geometry-locations"
    scope = _cleanup_run_scope(
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        check_id=check_id,
        project_ids=project_ids,
        project_slug=project,
        full_threshold=similarity_threshold,
        head_threshold=head_similarity_threshold,
    )
    run = _latest_succeeded_run_for_scope(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
        scope=scope,
    )
    if run is None:
        return _empty_location_issues_response(limit, offset)
    cached_rows, total = query_cached_check_results(
        session,
        run_id=str(run.id),
        stylebook_id=stylebook_id,
        check_id=check_id,
        limit=limit,
        offset=offset,
    )
    items: list[CleanupLocationGeographyIssueRow] = []
    for row in cached_rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        canonical_ids = row.canonical_ids_json or []
        if not canonical_ids:
            continue
        canonical_id = str(canonical_ids[0])
        canon = session.get(StylebookLocationCanonical, canonical_id)
        if canon is None:
            continue
        issue = payload.get("geography_issue", "missing_geometry")
        if issue not in ("missing_geometry", "distant_linked_places"):
            issue = "missing_geometry"
        items.append(
            CleanupLocationGeographyIssueRow(
                id=canonical_id,
                slug=str(canon.slug),
                label=str(row.label or canon.label),
                location_type=canon.location_type,
                status=str(canon.status),
                issue=issue,  # type: ignore[arg-type]
                distant_linked_count=int(payload.get("distant_linked_count", 0)),
            )
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
    check_id = "mismatched-people"
    scope = _cleanup_run_scope(
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        check_id=check_id,
        project_ids=project_ids,
        project_slug=project,
        full_threshold=similarity_threshold,
        head_threshold=head_similarity_threshold,
    )
    run = _latest_succeeded_run_for_scope(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
        scope=scope,
    )
    if run is None:
        return _empty_person_mismatch_response(limit, offset)
    cached_rows, total = query_cached_check_results(
        session,
        run_id=str(run.id),
        stylebook_id=stylebook_id,
        check_id=check_id,
        limit=limit,
        offset=offset,
    )
    items = _mismatch_items_from_cached_rows(
        session,
        cached_rows=cached_rows,
        entity_type="person",
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
    check_id = "mismatched-organizations"
    scope = _cleanup_run_scope(
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        check_id=check_id,
        project_ids=project_ids,
        project_slug=project,
        full_threshold=similarity_threshold,
        head_threshold=head_similarity_threshold,
    )
    run = _latest_succeeded_run_for_scope(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
        scope=scope,
    )
    if run is None:
        return _empty_organization_mismatch_response(limit, offset)
    cached_rows, total = query_cached_check_results(
        session,
        run_id=str(run.id),
        stylebook_id=stylebook_id,
        check_id=check_id,
        limit=limit,
        offset=offset,
    )
    items = _mismatch_items_from_cached_rows(
        session,
        cached_rows=cached_rows,
        entity_type="organization",
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
    "/{stylebook_slug}/cleanup/checks/questionable-person-canonicals",
    response_model=PaginatedCleanupQuestionablePeopleResponse,
)
def list_questionable_person_canonicals_check(
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
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(
        None,
        description="Optional label filter for questionable person canonicals.",
    ),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCleanupQuestionablePeopleResponse:
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
    check_id = "questionable-person-canonicals"
    scope = _cleanup_run_scope(
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        check_id=check_id,
        project_ids=project_ids,
        project_slug=project,
        full_threshold=similarity_threshold,
        head_threshold=head_similarity_threshold,
    )
    run = _latest_succeeded_run_for_scope(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
        scope=scope,
    )
    if run is None:
        return _empty_questionable_person_response(limit, offset)
    cached_rows, total = query_cached_check_results(
        session,
        run_id=str(run.id),
        stylebook_id=stylebook_id,
        check_id=check_id,
        limit=limit,
        offset=offset,
        query=q,
    )
    cids = sorted(
        {
            str(cid)
            for row in cached_rows
            for cid in (row.canonical_ids_json or [])
        }
    )
    rows_by_id = {
        cid: row
        for cid in cids
        if (row := session.get(StylebookPersonCanonical, cid)) is not None
    }
    canonicals = _questionable_person_responses_with_counts(
        session,
        project_ids=project_ids,
        rows_by_id=rows_by_id,
        cached_rows=cached_rows,
    )
    page = offset // limit + 1 if limit else 1
    return PaginatedCleanupQuestionablePeopleResponse(
        canonicals=canonicals,
        total=total,
        page=page,
        per_page=limit,
        has_next=offset + len(canonicals) < total,
        has_prev=offset > 0,
    )


@router.get(
    "/{stylebook_slug}/cleanup/checks/questionable-organization-canonicals",
    response_model=PaginatedCleanupQuestionableOrganizationsResponse,
)
def list_questionable_organization_canonicals_check(
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
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
    q: str | None = Query(
        None,
        description="Optional label filter for questionable organization canonicals.",
    ),
    session: Session = Depends(get_session),
    auth: dict[str, Any] = Depends(get_auth),
) -> PaginatedCleanupQuestionableOrganizationsResponse:
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
    check_id = "questionable-organization-canonicals"
    scope = _cleanup_run_scope(
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        check_id=check_id,
        project_ids=project_ids,
        project_slug=project,
        full_threshold=similarity_threshold,
        head_threshold=head_similarity_threshold,
    )
    run = _latest_succeeded_run_for_scope(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
        scope=scope,
    )
    if run is None:
        return _empty_questionable_organization_response(limit, offset)
    cached_rows, total = query_cached_check_results(
        session,
        run_id=str(run.id),
        stylebook_id=stylebook_id,
        check_id=check_id,
        limit=limit,
        offset=offset,
        query=q,
    )
    cids = sorted(
        {
            str(cid)
            for row in cached_rows
            for cid in (row.canonical_ids_json or [])
        }
    )
    rows_by_id = {
        cid: row
        for cid in cids
        if (row := session.get(StylebookOrganizationCanonical, cid)) is not None
    }
    canonicals = _questionable_organization_responses_with_counts(
        session,
        project_ids=project_ids,
        rows_by_id=rows_by_id,
        cached_rows=cached_rows,
    )
    page = offset // limit + 1 if limit else 1
    return PaginatedCleanupQuestionableOrganizationsResponse(
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
    check_id = "mismatched-locations"
    scope = _cleanup_run_scope(
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        check_id=check_id,
        project_ids=project_ids,
        project_slug=project,
        full_threshold=similarity_threshold,
        head_threshold=head_similarity_threshold,
    )
    run = _latest_succeeded_run_for_scope(
        session,
        stylebook_id=stylebook_id,
        check_id=check_id,
        scope=scope,
    )
    if run is None:
        return _empty_location_mismatch_response(limit, offset)
    cached_rows, total = query_cached_check_results(
        session,
        run_id=str(run.id),
        stylebook_id=stylebook_id,
        check_id=check_id,
        limit=limit,
        offset=offset,
    )
    items = _mismatch_items_from_cached_rows(
        session,
        cached_rows=cached_rows,
        entity_type="location",
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
    source_label = _canonical_label_for_entity(
        session,
        stylebook_id=int(sb.id),
        entity_type="location",
        canonical_id=source_canonical_id,
    )
    target_label = _canonical_label_for_entity(
        session,
        stylebook_id=int(sb.id),
        entity_type="location",
        canonical_id=body.target_canonical_id,
    )
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

    log_stylebook_activity_safe(
        session,
        stylebook_id=int(sb.id),
        actor_type="user",
        actor_user_id=_created_by_user_id(auth),
        source="cleanup_check",
        event_type=EVENT_CLEANUP_MERGE,
        entity_type="location",
        entity_id=result.source_id,
        entity_label=source_label,
        related_entity_type="location",
        related_entity_id=result.target_id,
        related_entity_label=target_label,
        payload_json={"check_id": "duplicate-locations"},
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
    log_stylebook_activity_safe(
        session,
        stylebook_id=int(sb.id),
        actor_type="user",
        actor_user_id=_created_by_user_id(auth),
        source="cleanup_check",
        event_type=EVENT_CLEANUP_DELETE,
        entity_type="location",
        entity_id=deleted_id,
        entity_label=str(canon.label),
        payload_json={"check_id": "questionable-location-canonicals"},
    )
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
    source_label = _canonical_label_for_entity(
        session,
        stylebook_id=int(sb.id),
        entity_type="person",
        canonical_id=source_canonical_id,
    )
    target_label = _canonical_label_for_entity(
        session,
        stylebook_id=int(sb.id),
        entity_type="person",
        canonical_id=body.target_canonical_id,
    )
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

    log_stylebook_activity_safe(
        session,
        stylebook_id=int(sb.id),
        actor_type="user",
        actor_user_id=_created_by_user_id(auth),
        source="cleanup_check",
        event_type=EVENT_CLEANUP_MERGE,
        entity_type="person",
        entity_id=result.source_id,
        entity_label=source_label,
        related_entity_type="person",
        related_entity_id=result.target_id,
        related_entity_label=target_label,
        payload_json={"check_id": "duplicate-people"},
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
    log_stylebook_activity_safe(
        session,
        stylebook_id=int(sb.id),
        actor_type="user",
        actor_user_id=_created_by_user_id(auth),
        source="cleanup_check",
        event_type=EVENT_CLEANUP_DELETE,
        entity_type="person",
        entity_id=deleted_id,
        entity_label=str(canon.label),
        payload_json={"check_id": "questionable-person-canonicals"},
    )
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
    source_label = _canonical_label_for_entity(
        session,
        stylebook_id=int(sb.id),
        entity_type="organization",
        canonical_id=source_canonical_id,
    )
    target_label = _canonical_label_for_entity(
        session,
        stylebook_id=int(sb.id),
        entity_type="organization",
        canonical_id=body.target_canonical_id,
    )
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

    log_stylebook_activity_safe(
        session,
        stylebook_id=int(sb.id),
        actor_type="user",
        actor_user_id=_created_by_user_id(auth),
        source="cleanup_check",
        event_type=EVENT_CLEANUP_MERGE,
        entity_type="organization",
        entity_id=result.source_id,
        entity_label=source_label,
        related_entity_type="organization",
        related_entity_id=result.target_id,
        related_entity_label=target_label,
        payload_json={"check_id": "duplicate-organizations"},
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
    log_stylebook_activity_safe(
        session,
        stylebook_id=int(sb.id),
        actor_type="user",
        actor_user_id=_created_by_user_id(auth),
        source="cleanup_check",
        event_type=EVENT_CLEANUP_DELETE,
        entity_type="organization",
        entity_id=deleted_id,
        entity_label=str(canon.label),
        payload_json={"check_id": "questionable-organization-canonicals"},
    )
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
        log_stylebook_activity_safe(
            session,
            stylebook_id=stylebook_id,
            actor_type="user",
            actor_user_id=user_id,
            source="cleanup_check",
            event_type=EVENT_CLEANUP_KEEP_SEPARATE,
            entity_type="check",
            entity_id=body.check_id,
            payload_json={
                "check_id": body.check_id,
                "member_ids": member_ids,
                "dismissed_pair_count": inserted,
            },
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
    log_stylebook_activity_safe(
        session,
        stylebook_id=stylebook_id,
        actor_type="user",
        actor_user_id=user_id,
        source="cleanup_check",
        event_type=EVENT_CLEANUP_KEEP,
        entity_type="check",
        entity_id=body.check_id,
        related_entity_type=check.entity_type,
        related_entity_id=canonical_id,
        related_entity_label=_canonical_label_for_entity(
            session,
            stylebook_id=stylebook_id,
            entity_type=check.entity_type,
            canonical_id=canonical_id,
        ),
        payload_json={"check_id": body.check_id, "canonical_id": canonical_id},
    )
    session.commit()
    return CleanupDismissalResponse(
        check_id=body.check_id,
        dismissed_canonical_id=canonical_id,
        message="Issue marked as reviewed",
    )
