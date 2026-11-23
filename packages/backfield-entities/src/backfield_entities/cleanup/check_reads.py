"""Cleanup check reads for keyed clients: the check list, cached results and run status.

These share the Stylebook UI's cached results, so a keyed client sees the same queue a person does
for the same scope (project and similarity thresholds).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from backfield_db import StylebookCleanupCheckResult, StylebookCleanupCheckRun
from pydantic import BaseModel, Field, JsonValue
from sqlmodel import Session

from backfield_entities.cleanup.cursor import decode_cursor, encode_cursor
from backfield_entities.cleanup.entity_models import (
    EntityName,
    cleanup_entity_models_for_singular,
)
from backfield_entities.cleanup.export import ExportFilters, canonical_ids_mentioned_in_range
from backfield_entities.quality.check_runs import (
    CleanupRunScope,
    cleanup_algorithm_version,
    cleanup_scope_hash,
    count_visible_cached_results,
    get_active_cleanup_check_run,
    get_latest_cleanup_check_run,
    get_latest_succeeded_cleanup_check_run,
    list_visible_cached_results,
    scope_to_json,
)
from backfield_entities.quality.checks import (
    STYLEBOOK_CLEANUP_CHECKS,
    CleanupCheckDef,
    cleanup_check_by_id,
)
from backfield_entities.quality.finders.duplicate_locations import (
    DEFAULT_FULL_SIMILARITY_THRESHOLD,
    DEFAULT_HEAD_SIMILARITY_THRESHOLD,
)

QueueScope = Literal["project", "stylebook"]
RESULTS_DEFAULT_LIMIT = 100
RESULTS_MAX_LIMIT = 500


class CheckSummary(BaseModel):
    id: str
    title: str
    description: str
    entity: EntityName
    kind: Literal["cluster", "list"]
    algorithm_version: str
    status: str = Field(description="`never_run`, `queued`, `running`, `succeeded` or `failed`.")
    open_count: int = Field(description="Open results in the last finished run.")
    run_id: str | None = None
    completed_at: datetime | None = None
    error_message: str | None = None


class CheckListOut(BaseModel):
    queue_scope: QueueScope
    checks: list[CheckSummary]


class CheckRunOut(BaseModel):
    id: str
    check_id: str
    status: str
    algorithm_version: str
    candidate_count: int
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime

    @classmethod
    def from_row(cls, row: StylebookCleanupCheckRun) -> CheckRunOut:
        return cls(
            id=str(row.id),
            check_id=str(row.check_id),
            status=str(row.status),
            algorithm_version=str(row.algorithm_version),
            candidate_count=int(row.candidate_count),
            error_message=row.error_message,
            started_at=row.started_at,
            completed_at=row.completed_at,
            created_at=row.created_at,
        )


class CheckResultItem(BaseModel):
    ordinal: int
    item_kind: Literal["cluster", "list"]
    item_key: str
    label: str | None
    canonical_ids: list[str]
    pair_keys: list[str]
    payload: dict[str, JsonValue] | None = Field(
        description="Why the item was flagged. Shape depends on the check."
    )


class CheckResultsPage(BaseModel):
    check_id: str
    algorithm_version: str
    queue_scope: QueueScope
    run_id: str | None = Field(description="The finished run these results come from.")
    as_of: datetime | None = Field(description="When that run finished (the results' watermark).")
    total: int = Field(description="Open results matching the filters, before paging.")
    items: list[CheckResultItem]
    next_cursor: str | None = None


class ResultsCursor(BaseModel):
    offset: int = Field(ge=0)


class UnknownCheckError(LookupError):
    """Raised for a check id the registry does not know."""


class CheckEnqueueError(RuntimeError):
    """Raised when a run was recorded but could not be handed to the worker."""


def require_check(check_id: str) -> CleanupCheckDef:
    check = cleanup_check_by_id(check_id.strip())
    if check is None:
        raise UnknownCheckError(f"Unknown cleanup check: {check_id}")
    return check


def entity_name_for_check(check: CleanupCheckDef) -> EntityName:
    return cleanup_entity_models_for_singular(check.entity_type).name


def build_run_scope(
    *,
    check_id: str,
    stylebook_id: int,
    organization_id: int,
    queue_scope: QueueScope,
    project_id: int,
    project_slug: str,
    full_threshold: float = DEFAULT_FULL_SIMILARITY_THRESHOLD,
    head_threshold: float = DEFAULT_HEAD_SIMILARITY_THRESHOLD,
) -> CleanupRunScope:
    """Scope identical to the one the Stylebook UI builds, so cached runs are shared."""
    is_project_scope = queue_scope == "project"
    return CleanupRunScope(
        stylebook_id=stylebook_id,
        organization_id=organization_id,
        check_id=check_id,
        full_threshold=full_threshold,
        head_threshold=head_threshold,
        project_ids=(project_id,) if is_project_scope else None,
        project_slug=project_slug if is_project_scope else None,
    )


def _summary(
    session: Session,
    check: CleanupCheckDef,
    *,
    scope: CleanupRunScope,
) -> CheckSummary:
    scope_hash = cleanup_scope_hash(scope)
    latest = get_latest_cleanup_check_run(
        session, stylebook_id=scope.stylebook_id, check_id=check.id, scope_hash=scope_hash
    )
    summary = CheckSummary(
        id=check.id,
        title=check.title,
        description=check.description,
        entity=entity_name_for_check(check),
        kind=check.kind,
        algorithm_version=cleanup_algorithm_version(check.id),
        status="never_run" if latest is None else str(latest.status),
        open_count=0,
        run_id=None if latest is None else str(latest.id),
        error_message=None if latest is None else latest.error_message,
    )
    # While a new pass is in flight, keep reporting the last finished one.
    finished = (
        latest
        if latest is not None and latest.status == "succeeded"
        else get_latest_succeeded_cleanup_check_run(
            session, stylebook_id=scope.stylebook_id, check_id=check.id, scope_hash=scope_hash
        )
    )
    if finished is not None:
        summary.open_count = count_visible_cached_results(
            session,
            run_id=str(finished.id),
            stylebook_id=scope.stylebook_id,
            check_id=check.id,
        )
        summary.completed_at = finished.completed_at
    return summary


def list_checks(
    session: Session,
    *,
    queue_scope: QueueScope,
    scope_for_check: Callable[[str], CleanupRunScope],
) -> CheckListOut:
    """Every check with its latest status and open count for the requested scope."""
    return CheckListOut(
        queue_scope=queue_scope,
        checks=[
            _summary(session, check, scope=scope_for_check(check.id))
            for check in STYLEBOOK_CLEANUP_CHECKS
        ],
    )


def _result_item(row: StylebookCleanupCheckResult) -> CheckResultItem:
    return CheckResultItem(
        ordinal=int(row.ordinal),
        item_kind=row.item_kind,
        item_key=str(row.item_key),
        label=row.label,
        canonical_ids=[str(i) for i in row.canonical_ids_json or []],
        pair_keys=[str(k) for k in row.pair_keys_json or []],
        payload=row.payload_json,
    )


def get_check_results(
    session: Session,
    check: CleanupCheckDef,
    *,
    scope: CleanupRunScope,
    queue_scope: QueueScope,
    filters: ExportFilters,
    query: str | None,
    cursor: str | None,
    limit: int,
) -> CheckResultsPage:
    """One page of open results from the last finished run, optionally date-filtered.

    Raises ``InvalidCursorError`` when ``cursor`` cannot be decoded.
    """
    offset = decode_cursor(cursor, ResultsCursor).offset if cursor else 0
    empty = CheckResultsPage(
        check_id=check.id,
        algorithm_version=cleanup_algorithm_version(check.id),
        queue_scope=queue_scope,
        run_id=None,
        as_of=None,
        total=0,
        items=[],
    )
    run = get_latest_succeeded_cleanup_check_run(
        session,
        stylebook_id=scope.stylebook_id,
        check_id=check.id,
        scope_hash=cleanup_scope_hash(scope),
    )
    if run is None:
        return empty
    visible = list_visible_cached_results(
        session,
        run_id=str(run.id),
        stylebook_id=scope.stylebook_id,
        check_id=check.id,
        query=query,
    )
    if filters.mentioned_from is not None or filters.mentioned_to is not None:
        visible = _within_mention_range(session, check, visible, filters)
    page = visible[offset : offset + limit]
    has_more = offset + limit < len(visible)
    return CheckResultsPage(
        check_id=check.id,
        algorithm_version=str(run.algorithm_version),
        queue_scope=queue_scope,
        run_id=str(run.id),
        as_of=run.completed_at,
        total=len(visible),
        items=[_result_item(row) for row in page],
        next_cursor=encode_cursor(ResultsCursor(offset=offset + limit)) if has_more else None,
    )


def _within_mention_range(
    session: Session,
    check: CleanupCheckDef,
    results: list[StylebookCleanupCheckResult],
    filters: ExportFilters,
) -> list[StylebookCleanupCheckResult]:
    """Keep results where at least one member canonical has a mention in the date range."""
    models = cleanup_entity_models_for_singular(check.entity_type)
    member_ids = {str(cid) for row in results for cid in row.canonical_ids_json or []}
    in_range = canonical_ids_mentioned_in_range(session, models, member_ids, filters)
    return [
        row for row in results if any(str(cid) in in_range for cid in row.canonical_ids_json or [])
    ]


def start_check_run(
    session: Session,
    check: CleanupCheckDef,
    *,
    scope: CleanupRunScope,
    created_by_user_id: int | None,
    enqueue: Callable[[str], None],
) -> CheckRunOut:
    """Queue a run for the scope, or return the one already in flight."""
    scope_hash = cleanup_scope_hash(scope)
    active = get_active_cleanup_check_run(
        session, stylebook_id=scope.stylebook_id, check_id=check.id, scope_hash=scope_hash
    )
    if active is not None:
        return CheckRunOut.from_row(active)
    run = StylebookCleanupCheckRun(
        id=str(uuid.uuid4()),
        stylebook_id=scope.stylebook_id,
        check_id=check.id,
        status="queued",
        scope_hash=scope_hash,
        scope_json=scope_to_json(scope),
        algorithm_version=cleanup_algorithm_version(check.id),
        created_by_user_id=created_by_user_id,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    try:
        enqueue(str(run.id))
    except Exception as exc:  # broker errors vary; never leave a run stuck in `queued`
        run.status = "failed"
        run.error_message = "The run could not be queued."
        session.add(run)
        session.commit()
        raise CheckEnqueueError(run.error_message) from exc
    return CheckRunOut.from_row(run)


def latest_check_run(
    session: Session, check: CleanupCheckDef, *, scope: CleanupRunScope
) -> CheckRunOut | None:
    """The newest run for the scope, whatever its status."""
    row = get_latest_cleanup_check_run(
        session,
        stylebook_id=scope.stylebook_id,
        check_id=check.id,
        scope_hash=cleanup_scope_hash(scope),
    )
    return None if row is None else CheckRunOut.from_row(row)
