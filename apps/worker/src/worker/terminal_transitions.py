"""Guarded Agate run/item terminal transitions with EMF emission."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from backfield_auth.structured_logging import log_event
from backfield_db import AgateProcessedItem, AgateRun
from backfield_observability.lifecycle import emit_item_terminal, emit_run_terminal, worker_identity
from sqlmodel import Session

logger = logging.getLogger(__name__)

_RUN_CANCELLED_MESSAGE = "Run cancelled by user"
_CANCELLED_PREFIXES = (_RUN_CANCELLED_MESSAGE,)


def is_cancelled_message(message: str | None) -> bool:
    if not message:
        return False
    return any(message.startswith(prefix) for prefix in _CANCELLED_PREFIXES)


def apply_item_terminal_status(
    session: Session,
    item: AgateProcessedItem,
    *,
    new_status: str,
    error_message: str | None,
    result_json: str | None = None,
    substrate_article_id: int | None = None,
    clear_result: bool = False,
) -> bool:
    """Write an item terminal status only when the row is still mutable.

    Returns True when the transition was applied and committed by the caller.
    """
    previous = item.status
    if previous not in ("pending", "running"):
        log_event(
            logger,
            "item_terminal_skipped",
            item_id=str(item.id) if item.id is not None else None,
            run_id=item.run_id,
            previous_status=previous,
            attempted_status=new_status,
            reason="already_terminal",
        )
        return False
    if is_cancelled_message(item.error_message):
        log_event(
            logger,
            "item_terminal_skipped",
            item_id=str(item.id) if item.id is not None else None,
            run_id=item.run_id,
            previous_status=previous,
            attempted_status=new_status,
            reason="cancelled",
        )
        return False

    finished_at = datetime.now(UTC)
    item.status = new_status
    item.error_message = error_message
    if clear_result or new_status == "failed":
        item.result_json = None
        item.substrate_article_id = None
    else:
        if result_json is not None:
            item.result_json = result_json
        if substrate_article_id is not None:
            item.substrate_article_id = substrate_article_id
    item.updated_at = finished_at
    session.add(item)
    return True


def emit_item_terminal_after_commit(
    item: AgateProcessedItem,
    *,
    previous_status: str,
    finished_at: datetime | None = None,
) -> None:
    finished = finished_at or item.updated_at or datetime.now(UTC)
    emit_item_terminal(
        previous_status=previous_status,
        new_status=item.status,
        identity=worker_identity(),
        started_at=item.started_at,
        finished_at=finished,
        correlation={
            "run_id": item.run_id,
            "item_id": str(item.id) if item.id is not None else "",
        },
    )


def apply_run_terminal_status(
    session: Session,
    run: AgateRun,
    *,
    new_status: str,
    error_message: str | None,
    result_json: str | None | object = ...,
) -> bool:
    """Write a run terminal status only when the run is still pending/running."""
    previous = run.status
    if previous not in ("pending", "running"):
        log_event(
            logger,
            "run_terminal_skipped",
            run_id=run.id,
            previous_status=previous,
            attempted_status=new_status,
            reason="already_terminal",
        )
        return False
    if is_cancelled_message(run.error_message):
        log_event(
            logger,
            "run_terminal_skipped",
            run_id=run.id,
            previous_status=previous,
            attempted_status=new_status,
            reason="cancelled",
        )
        return False

    run.status = new_status
    run.error_message = error_message
    if result_json is not ...:
        run.result_json = result_json  # type: ignore[assignment]
    run.updated_at = datetime.now(UTC)
    session.add(run)
    return True


def emit_run_terminal_after_commit(
    run: AgateRun,
    *,
    previous_status: str,
) -> None:
    emit_run_terminal(
        previous_status=previous_status,
        new_status=run.status,
        identity=worker_identity(),
        correlation={"run_id": run.id},
    )


def commit_item_terminal(
    session: Session,
    item: AgateProcessedItem,
    *,
    previous_status: str,
    new_status: str,
    error_message: str | None,
    result_json: str | None = None,
    substrate_article_id: int | None = None,
    clear_result: bool = False,
) -> bool:
    applied = apply_item_terminal_status(
        session,
        item,
        new_status=new_status,
        error_message=error_message,
        result_json=result_json,
        substrate_article_id=substrate_article_id,
        clear_result=clear_result,
    )
    if not applied:
        return False
    session.commit()
    emit_item_terminal_after_commit(item, previous_status=previous_status)
    return True


def commit_run_terminal(
    session: Session,
    run: AgateRun,
    *,
    previous_status: str,
    new_status: str,
    error_message: str | None,
    result_json: str | None | object = ...,
) -> bool:
    applied = apply_run_terminal_status(
        session,
        run,
        new_status=new_status,
        error_message=error_message,
        result_json=result_json,
    )
    if not applied:
        return False
    session.commit()
    emit_run_terminal_after_commit(run, previous_status=previous_status)
    return True
