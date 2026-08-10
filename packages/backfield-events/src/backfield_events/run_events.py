"""Run-attempt output snapshots and the shared run-terminal event recorder.

Callers invoke these inside the same open transaction that writes run terminal
state (worker terminal paths and the API cancellation path) so the event and
output snapshot commit atomically with the run.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    AgateRunOutputArticle,
    BackfieldProject,
)
from sqlalchemy import func
from sqlmodel import Session, select

from backfield_events.config import webhooks_enabled
from backfield_events.contracts import RunCompletedCounts, normalize_run_outcome
from backfield_events.recording import RecordedEvent, record_run_completed_event

#: Shared cancellation marker (see worker terminal_transitions and Agate API cancel).
RUN_CANCELLED_MESSAGE = "Run cancelled by user"

TERMINAL_RUN_STATUSES = ("succeeded", "failed", "timed_out")


def record_run_output_article(
    session: Session,
    *,
    run_id: str,
    execution_attempt: int,
    article_id: int,
    processed_item_id: int | None,
) -> bool:
    """Associate a persisted article with the run attempt; False when already recorded."""
    existing = session.exec(
        select(AgateRunOutputArticle.id).where(
            AgateRunOutputArticle.run_id == run_id,
            AgateRunOutputArticle.execution_attempt == execution_attempt,
            AgateRunOutputArticle.article_id == article_id,
        )
    ).first()
    if existing is not None:
        return False
    session.add(
        AgateRunOutputArticle(
            run_id=run_id,
            execution_attempt=execution_attempt,
            article_id=article_id,
            processed_item_id=processed_item_id,
        )
    )
    return True


def materialize_run_output_snapshot(session: Session, run: AgateRun) -> int:
    """Complete the attempt's successful-output snapshot; returns the article count.

    Copies current succeeded processed-item article links into the immutable
    per-attempt association table, preserving rows already written by DBOutput
    during the run. Prior attempts are never modified.
    """
    attempt = int(run.execution_attempt or 1)
    existing = {
        int(article_id)
        for article_id in session.exec(
            select(AgateRunOutputArticle.article_id).where(
                AgateRunOutputArticle.run_id == run.id,
                AgateRunOutputArticle.execution_attempt == attempt,
            )
        ).all()
    }
    rows = session.exec(
        select(AgateProcessedItem.id, AgateProcessedItem.substrate_article_id).where(
            AgateProcessedItem.run_id == run.id,
            AgateProcessedItem.status == "succeeded",
            AgateProcessedItem.substrate_article_id.is_not(None),  # type: ignore[union-attr]
        )
    ).all()
    for item_id, article_id in rows:
        if article_id is None or int(article_id) in existing:
            continue
        session.add(
            AgateRunOutputArticle(
                run_id=run.id,
                execution_attempt=attempt,
                article_id=int(article_id),
                processed_item_id=int(item_id) if item_id is not None else None,
            )
        )
        existing.add(int(article_id))
    session.flush()
    return len(existing)


def record_run_terminal_event(session: Session, run: AgateRun) -> RecordedEvent | None:
    """Record the run-completed event for a run already set to a terminal status.

    Always materializes the attempt's output snapshot (the public run-articles
    endpoint depends on it); the event and webhook deliveries are only written
    when webhooks are enabled. Returns None when no event was recorded.
    """
    if run.status not in TERMINAL_RUN_STATUSES:
        return None

    article_count = materialize_run_output_snapshot(session, run)
    if not webhooks_enabled():
        return None

    graph = session.get(AgateGraph, run.graph_id)
    if graph is None:
        return None
    project = session.get(BackfieldProject, graph.project_id)
    if project is None:
        return None

    cancelled = bool(run.error_message and run.error_message.startswith(RUN_CANCELLED_MESSAGE))
    outcome, completion_reason = normalize_run_outcome(status=run.status, cancelled=cancelled)
    failure_category = _failure_category(status=run.status, completion_reason=completion_reason)

    return record_run_completed_event(
        session,
        run=run,
        graph=graph,
        project=project,
        outcome=outcome,
        completion_reason=completion_reason,
        failure_category=failure_category,
        counts=_run_counts(session, run),
        article_count=article_count,
        occurred_at=datetime.now(UTC),
    )


def _failure_category(*, status: str, completion_reason: str) -> str | None:
    """Normalized safe category; never raw status or provider error text."""
    if completion_reason == "completed":
        return None
    if completion_reason == "cancelled":
        return "cancelled"
    if status == "timed_out":
        return "timeout"
    return "execution_error"


def _run_counts(session: Session, run: AgateRun) -> RunCompletedCounts:
    """Item counts per terminal status; whole-graph runs report a single unit."""
    rows = session.exec(
        select(AgateProcessedItem.status, func.count())
        .where(AgateProcessedItem.run_id == run.id)
        .group_by(AgateProcessedItem.status)
    ).all()
    if rows:
        total = succeeded = failed = 0
        for status, count in rows:
            n = int(count)
            total += n
            if status == "succeeded":
                succeeded += n
            elif status in ("failed", "timed_out"):
                failed += n
        return RunCompletedCounts(total=total, succeeded=succeeded, failed=failed)

    if run.status == "succeeded":
        return RunCompletedCounts(total=1, succeeded=1, failed=0)
    return RunCompletedCounts(total=1, succeeded=0, failed=1)
