"""Cleanup runs and the action ledger: open, close, and read back what was applied."""

from __future__ import annotations

from backfield_entities.cleanup.cursor import InvalidCursorError
from backfield_entities.cleanup.runs import (
    RUNS_DEFAULT_LIMIT,
    RUNS_MAX_LIMIT,
    ActionOut,
    ActionPage,
    ClosingStatus,
    RunNotFoundError,
    RunOut,
    RunPage,
    RunStateError,
    RunStatus,
    close_run,
    get_action,
    list_actions,
    list_runs,
    open_run,
    require_run,
    run_out,
)
from fastapi import Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session

from core_api.deps import get_session
from core_api.routers.public.cleanup.deps import (
    CleanupContext,
    action_caller,
    get_cleanup_context,
    require_cleanup_apply,
    require_cleanup_read,
)


class OpenRunRequest(BaseModel):
    label: str | None = Field(default=None, max_length=200, description="A name for the run.")
    client_run_ref: str | None = Field(
        default=None, max_length=200, description="Your own reference, stored as given."
    )


class CloseRunRequest(BaseModel):
    status: ClosingStatus = Field(
        default="closed",
        description="`aborted` is the kill switch: no further changes are accepted on the run.",
    )


def _run_not_found() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")


def post_cleanup_run(
    body: OpenRunRequest,
    _auth: dict = Depends(require_cleanup_apply),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
) -> RunOut:
    """Open a run. Every change you apply belongs to one."""
    caller = action_caller(context.auth)
    run = open_run(
        session,
        stylebook_id=context.stylebook_id,
        label=body.label,
        client_run_ref=body.client_run_ref,
        credential_id=caller.credential_id,
        credential_label=caller.credential_label,
    )
    session.commit()
    return run_out(session, run)


def post_cleanup_run_close(
    run_id: str,
    body: CloseRunRequest,
    _auth: dict = Depends(require_cleanup_apply),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
) -> RunOut:
    """Close a run, or abort it to stop further changes right away."""
    try:
        run = close_run(
            session, stylebook_id=context.stylebook_id, run_id=run_id, status=body.status
        )
    except RunNotFoundError as exc:
        raise _run_not_found() from exc
    except RunStateError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    session.commit()
    return run_out(session, run)


def get_cleanup_runs(
    _auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
    run_status: RunStatus | None = Query(default=None, alias="status"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=RUNS_DEFAULT_LIMIT, ge=1, le=RUNS_MAX_LIMIT),
) -> RunPage:
    """Runs in this Stylebook, newest first."""
    try:
        return list_runs(
            session,
            stylebook_id=context.stylebook_id,
            status=run_status,
            cursor=cursor,
            limit=limit,
        )
    except InvalidCursorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def get_cleanup_run(
    run_id: str,
    _auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
) -> RunOut:
    try:
        run = require_run(session, stylebook_id=context.stylebook_id, run_id=run_id)
    except RunNotFoundError as exc:
        raise _run_not_found() from exc
    return run_out(session, run)


def get_cleanup_run_actions(
    run_id: str,
    _auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=RUNS_DEFAULT_LIMIT, ge=1, le=RUNS_MAX_LIMIT),
) -> ActionPage:
    """What was applied in a run, oldest first. Read this after a crash to see what landed."""
    try:
        return list_actions(
            session,
            stylebook_id=context.stylebook_id,
            run_id=run_id,
            cursor=cursor,
            limit=limit,
        )
    except RunNotFoundError as exc:
        raise _run_not_found() from exc
    except InvalidCursorError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def get_cleanup_action(
    action_id: str,
    _auth: dict = Depends(require_cleanup_read),
    context: CleanupContext = Depends(get_cleanup_context),
    session: Session = Depends(get_session),
) -> ActionOut:
    """One applied action, including what the records looked like before the change."""
    action = get_action(session, stylebook_id=context.stylebook_id, action_id=action_id)
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    return action
