"""Cleanup check reads: the check list, cached results and run status."""

from __future__ import annotations

from datetime import date
from typing import Any

from backfield_entities.cleanup.check_reads import (
    DEFAULT_FULL_SIMILARITY_THRESHOLD,
    DEFAULT_HEAD_SIMILARITY_THRESHOLD,
    RESULTS_DEFAULT_LIMIT,
    RESULTS_MAX_LIMIT,
    CheckEnqueueError,
    CheckListOut,
    CheckResultsPage,
    CheckRunOut,
    QueueScope,
    UnknownCheckError,
    build_run_scope,
    get_check_results,
    latest_check_run,
    list_checks,
    require_check,
    start_check_run,
)
from backfield_entities.cleanup.cursor import InvalidCursorError
from backfield_entities.cleanup.export import ExportFilters
from backfield_entities.quality.check_runs import CleanupRunScope
from backfield_entities.quality.checks import CleanupCheckDef
from fastapi import Depends, HTTPException, Query, status
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.cleanup.deps import (
    CleanupContext,
    get_cleanup_context,
    is_service_principal,
    require_cleanup_read,
)
from core_api.run_enqueue import enqueue_worker_task

EXECUTE_CHECK_RUN_TASK = "worker.tasks.execute_cleanup_check_run"


class CheckScopeParams:
    """Query parameters that decide which cached run a request reads or starts."""

    def __init__(
        self,
        scope: QueueScope = Query(
            default="project",
            description=(
                "`project` limits list checks to the key's project. `stylebook` covers every "
                "project and needs a service key."
            ),
        ),
        similarity_threshold: float = Query(
            default=DEFAULT_FULL_SIMILARITY_THRESHOLD,
            ge=0.5,
            le=0.95,
            description="Minimum full-name similarity for near-duplicate clusters.",
        ),
        head_similarity_threshold: float = Query(
            default=DEFAULT_HEAD_SIMILARITY_THRESHOLD,
            ge=0.5,
            le=0.95,
            description="Minimum primary-name similarity (text before the first comma).",
        ),
    ) -> None:
        self.scope = scope
        self.similarity_threshold = similarity_threshold
        self.head_similarity_threshold = head_similarity_threshold


def _require_scope_allowed(auth: dict[str, Any], scope: QueueScope) -> None:
    if scope == "stylebook" and not is_service_principal(auth):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Stylebook-wide queues need a service key.",
        )


def _run_scope(context: CleanupContext, params: CheckScopeParams, check_id: str) -> CleanupRunScope:
    return build_run_scope(
        check_id=check_id,
        stylebook_id=context.stylebook_id,
        organization_id=int(context.project.organization_id),
        queue_scope=params.scope,
        project_id=int(context.project.id),
        project_slug=str(context.project.slug),
        full_threshold=params.similarity_threshold,
        head_threshold=params.head_similarity_threshold,
    )


def _check_or_404(check_id: str) -> CleanupCheckDef:
    try:
        return require_check(check_id)
    except UnknownCheckError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def get_cleanup_checks(
    auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
    params: CheckScopeParams = Depends(),
) -> CheckListOut:
    """Every check with its algorithm version, latest status and open count."""
    _require_scope_allowed(auth, params.scope)
    return list_checks(
        session,
        queue_scope=params.scope,
        scope_for_check=lambda check_id: _run_scope(context, params, check_id),
    )


def get_cleanup_check_results(
    check_id: str,
    auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
    params: CheckScopeParams = Depends(),
    cursor: str | None = Query(default=None, description="`next_cursor` from the previous page."),
    limit: int = Query(default=RESULTS_DEFAULT_LIMIT, ge=1, le=RESULTS_MAX_LIMIT),
    q: str | None = Query(default=None, description="Filter results by label text."),
    mentioned_from: date | None = Query(default=None),
    mentioned_to: date | None = Query(default=None),
) -> CheckResultsPage:
    """Open results from the last finished run, with the run's algorithm version and time."""
    _require_scope_allowed(auth, params.scope)
    check = _check_or_404(check_id)
    try:
        return get_check_results(
            session,
            check,
            scope=_run_scope(context, params, check.id),
            queue_scope=params.scope,
            filters=ExportFilters(mentioned_from=mentioned_from, mentioned_to=mentioned_to),
            query=q,
            cursor=cursor,
            limit=limit,
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def post_cleanup_check_run(
    check_id: str,
    auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
    params: CheckScopeParams = Depends(),
) -> CheckRunOut:
    """Start a check run for the scope, or return the one already running."""
    _require_scope_allowed(auth, params.scope)
    check = _check_or_404(check_id)
    try:
        return start_check_run(
            session,
            check,
            scope=_run_scope(context, params, check.id),
            created_by_user_id=None,
            enqueue=lambda run_id: enqueue_worker_task(EXECUTE_CHECK_RUN_TASK, [run_id]),
        )
    except CheckEnqueueError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


def get_cleanup_check_latest_run(
    check_id: str,
    auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
    params: CheckScopeParams = Depends(),
) -> CheckRunOut:
    """Status of the newest run for the scope; 404 when the check has never run."""
    _require_scope_allowed(auth, params.scope)
    check = _check_or_404(check_id)
    run = latest_check_run(session, check, scope=_run_scope(context, params, check.id))
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No run yet")
    return run
