"""Runs and ledger reads: a run is a caller-opened grouping of applied actions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal, cast

from backfield_db import StylebookCleanupAction, StylebookCleanupRun
from pydantic import BaseModel, Field, JsonValue
from sqlalchemy import and_, func, or_
from sqlmodel import Session, col, select

from backfield_entities.cleanup.cursor import InvalidCursorError, decode_cursor, encode_cursor

RunStatus = Literal["open", "closed", "aborted"]
ClosingStatus = Literal["closed", "aborted"]
RUNS_DEFAULT_LIMIT = 50
RUNS_MAX_LIMIT = 200


class RunOut(BaseModel):
    id: str
    label: str | None
    client_run_ref: str | None
    status: RunStatus
    credential_label: str | None
    created_at: datetime
    closed_at: datetime | None
    action_counts: dict[str, int] = Field(description="Applied actions by operation class.")


class RunPage(BaseModel):
    items: list[RunOut]
    next_cursor: str | None = None


class ActionOut(BaseModel):
    """A ledger row. ``before_state`` is only returned when one action is read on its own."""

    id: str
    run_id: str
    operation: str
    entity_type: str
    canonical_id: str | None
    related_canonical_id: str | None
    client_item_id: str | None
    provenance: dict[str, JsonValue] | None
    credential_label: str | None
    request: dict[str, JsonValue]
    result: dict[str, JsonValue]
    reindex_queued: bool
    created_at: datetime
    undone_at: datetime | None
    before_state: dict[str, JsonValue] | None = None


class ActionPage(BaseModel):
    items: list[ActionOut]
    next_cursor: str | None = None


class RunsCursor(BaseModel):
    after_id: str


class RunNotFoundError(LookupError):
    """The run does not exist in this Stylebook."""


class RunStateError(ValueError):
    """The run cannot move to the requested status."""


def open_run(
    session: Session,
    *,
    stylebook_id: int,
    label: str | None,
    client_run_ref: str | None,
    credential_id: int | None,
    credential_label: str | None,
) -> StylebookCleanupRun:
    run = StylebookCleanupRun(
        stylebook_id=stylebook_id,
        label=label,
        client_run_ref=client_run_ref,
        credential_id=credential_id,
        credential_label=credential_label,
    )
    session.add(run)
    session.flush()
    return run


def require_run(session: Session, *, stylebook_id: int, run_id: str) -> StylebookCleanupRun:
    run = session.get(StylebookCleanupRun, run_id)
    if run is None or int(run.stylebook_id) != int(stylebook_id):
        raise RunNotFoundError("Run not found.")
    return run


def close_run(
    session: Session, *, stylebook_id: int, run_id: str, status: ClosingStatus
) -> StylebookCleanupRun:
    """Close or abort an open run. Repeating the same request is fine; switching is not."""
    run = require_run(session, stylebook_id=stylebook_id, run_id=run_id)
    if run.status == status:
        return run
    if run.status != "open":
        raise RunStateError(f"The run is already {run.status}.")
    run.status = status
    run.closed_at = datetime.now(UTC)
    session.add(run)
    session.flush()
    return run


def _action_counts(session: Session, run_ids: list[str]) -> dict[str, dict[str, int]]:
    if not run_ids:
        return {}
    rows = session.exec(
        select(StylebookCleanupAction.run_id, StylebookCleanupAction.operation, func.count())
        .where(col(StylebookCleanupAction.run_id).in_(run_ids))
        .group_by(StylebookCleanupAction.run_id, StylebookCleanupAction.operation)
    ).all()
    counts: dict[str, dict[str, int]] = {}
    for run_id, operation, count in rows:
        counts.setdefault(str(run_id), {})[str(operation)] = int(count)
    return counts


def _run_out(run: StylebookCleanupRun, counts: dict[str, int]) -> RunOut:
    return RunOut(
        id=str(run.id),
        label=run.label,
        client_run_ref=run.client_run_ref,
        status=cast(RunStatus, run.status),
        credential_label=run.credential_label,
        created_at=run.created_at,
        closed_at=run.closed_at,
        action_counts=counts,
    )


def run_out(session: Session, run: StylebookCleanupRun) -> RunOut:
    return _run_out(run, _action_counts(session, [str(run.id)]).get(str(run.id), {}))


def _after_id(cursor: str | None) -> str | None:
    return decode_cursor(cursor, RunsCursor).after_id if cursor else None


def _run_after(
    session: Session, cursor: str | None, stylebook_id: int
) -> StylebookCleanupRun | None:
    after_id = _after_id(cursor)
    if after_id is None:
        return None
    run = session.get(StylebookCleanupRun, after_id)
    if run is None or int(run.stylebook_id) != int(stylebook_id):
        raise InvalidCursorError("Invalid cursor.")
    return run


def _action_after(
    session: Session, cursor: str | None, run_id: str
) -> StylebookCleanupAction | None:
    after_id = _after_id(cursor)
    if after_id is None:
        return None
    action = session.get(StylebookCleanupAction, after_id)
    if action is None or str(action.run_id) != run_id:
        raise InvalidCursorError("Invalid cursor.")
    return action


def list_runs(
    session: Session,
    *,
    stylebook_id: int,
    status: RunStatus | None,
    cursor: str | None,
    limit: int,
) -> RunPage:
    """Newest runs first. Raises ``InvalidCursorError`` for a cursor that points nowhere."""
    statement = select(StylebookCleanupRun).where(StylebookCleanupRun.stylebook_id == stylebook_id)
    if status is not None:
        statement = statement.where(StylebookCleanupRun.status == status)
    after = _run_after(session, cursor, stylebook_id)
    if after is not None:
        statement = statement.where(
            or_(
                col(StylebookCleanupRun.created_at) < after.created_at,
                and_(
                    StylebookCleanupRun.created_at == after.created_at,
                    col(StylebookCleanupRun.id) < after.id,
                ),
            )
        )
    rows = session.exec(
        statement.order_by(
            col(StylebookCleanupRun.created_at).desc(), col(StylebookCleanupRun.id).desc()
        ).limit(limit + 1)
    ).all()
    page = rows[:limit]
    counts = _action_counts(session, [str(r.id) for r in page])
    return RunPage(
        items=[_run_out(r, counts.get(str(r.id), {})) for r in page],
        next_cursor=encode_cursor(RunsCursor(after_id=str(page[-1].id)))
        if len(rows) > limit
        else None,
    )


def action_out(action: StylebookCleanupAction, *, include_before_state: bool) -> ActionOut:
    return ActionOut(
        id=str(action.id),
        run_id=str(action.run_id),
        operation=action.operation,
        entity_type=action.entity_type,
        canonical_id=action.canonical_id,
        related_canonical_id=action.related_canonical_id,
        client_item_id=action.client_item_id,
        provenance=action.provenance_json,
        credential_label=action.credential_label,
        request=action.request_json,
        result=action.result_json,
        reindex_queued=bool(action.reindex_queued),
        created_at=action.created_at,
        undone_at=action.undone_at,
        before_state=action.before_state_json if include_before_state else None,
    )


def list_actions(
    session: Session, *, stylebook_id: int, run_id: str, cursor: str | None, limit: int
) -> ActionPage:
    """A run's ledger, oldest first. Raises ``RunNotFoundError`` and ``InvalidCursorError``."""
    require_run(session, stylebook_id=stylebook_id, run_id=run_id)
    statement = select(StylebookCleanupAction).where(StylebookCleanupAction.run_id == run_id)
    after = _action_after(session, cursor, run_id)
    if after is not None:
        statement = statement.where(
            or_(
                col(StylebookCleanupAction.created_at) > after.created_at,
                and_(
                    StylebookCleanupAction.created_at == after.created_at,
                    col(StylebookCleanupAction.id) > after.id,
                ),
            )
        )
    rows = session.exec(
        statement.order_by(
            col(StylebookCleanupAction.created_at).asc(), col(StylebookCleanupAction.id).asc()
        ).limit(limit + 1)
    ).all()
    page = rows[:limit]
    return ActionPage(
        items=[action_out(a, include_before_state=False) for a in page],
        next_cursor=encode_cursor(RunsCursor(after_id=str(page[-1].id)))
        if len(rows) > limit
        else None,
    )


def get_action(session: Session, *, stylebook_id: int, action_id: str) -> ActionOut | None:
    action = session.get(StylebookCleanupAction, action_id)
    if action is None or int(action.stylebook_id) != int(stylebook_id):
        return None
    return action_out(action, include_before_state=True)
