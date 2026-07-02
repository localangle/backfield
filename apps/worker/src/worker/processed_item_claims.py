"""Helpers for ``agate_processed_item`` running-claim lifecycle in the worker."""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime

from backfield_db import AgateProcessedItem
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

_EXECUTE_PROCESSED_ITEM_TASK = "worker.tasks.execute_processed_item"
_ORPHAN_RUNNING_AFTER_S = int(os.getenv("BATCH_ORPHAN_RUNNING_AFTER_S", "120"))
_ORPHAN_RECONCILE_INTERVAL_S = float(os.getenv("BATCH_ORPHAN_RECONCILE_INTERVAL_S", "30"))
_WORKER_CONCURRENCY = int(os.getenv("CELERY_WORKER_CONCURRENCY", "16"))

_orphan_reconcile_last_by_run: dict[str, float] = {}


def running_item_touch_ts(item: AgateProcessedItem) -> datetime:
    return item.started_at or item.updated_at or item.created_at


def is_orphan_running_item(
    item: AgateProcessedItem,
    *,
    active_item_ids: set[int],
    now: datetime | None = None,
    orphan_after_s: int = _ORPHAN_RUNNING_AFTER_S,
) -> bool:
    if item.status != "running" or item.id is None:
        return False
    if int(item.id) in active_item_ids:
        return False
    now = now or datetime.now(UTC)
    touch = running_item_touch_ts(item)
    if touch.tzinfo is None:
        touch = touch.replace(tzinfo=UTC)
    return (now - touch).total_seconds() >= float(orphan_after_s)


def should_reconcile_orphan_running_items(
    running_count: int,
    *,
    run_id: str,
    concurrency: int = _WORKER_CONCURRENCY,
) -> bool:
    if running_count <= concurrency:
        return False
    now = time.monotonic()
    last = _orphan_reconcile_last_by_run.get(run_id, 0.0)
    if now - last < _ORPHAN_RECONCILE_INTERVAL_S:
        return False
    _orphan_reconcile_last_by_run[run_id] = now
    return True


def release_running_claim(session: Session, item_id: int, *, now: datetime | None = None) -> bool:
    """Return a claimed item to ``pending`` so UI counts and retries stay accurate."""
    item = session.get(AgateProcessedItem, item_id)
    if item is None or item.status != "running":
        return False
    now = now or datetime.now(UTC)
    item.status = "pending"
    item.started_at = None
    item.error_message = None
    item.updated_at = now
    session.add(item)
    return True


def release_orphan_running_items_for_run(
    session: Session,
    run_id: str,
    *,
    active_item_ids: set[int],
    now: datetime | None = None,
) -> int:
    rows = list(
        session.exec(
            select(AgateProcessedItem).where(
                AgateProcessedItem.run_id == run_id,
                AgateProcessedItem.status == "running",
            )
        ).all()
    )
    released = 0
    for row in rows:
        if not is_orphan_running_item(row, active_item_ids=active_item_ids, now=now):
            continue
        if row.id is None:
            continue
        if release_running_claim(session, int(row.id), now=now):
            released += 1
            logger.info(
                "Released orphan running processed_item id=%s run_id=%s back to pending",
                row.id,
                run_id,
            )
    return released


def active_execute_processed_item_ids(celery_app: object) -> set[int]:
    """Best-effort snapshot of item ids currently executing in this worker pool."""
    try:
        inspect = celery_app.control.inspect(timeout=1.0)  # type: ignore[attr-defined]
        active = inspect.active()
    except Exception:
        logger.debug("Could not inspect active Celery tasks for orphan reconcile", exc_info=True)
        return set()
    if not active:
        return set()
    ids: set[int] = set()
    for tasks in active.values():
        for task in tasks or []:
            if task.get("name") != _EXECUTE_PROCESSED_ITEM_TASK:
                continue
            args = task.get("args") or []
            if not args:
                continue
            try:
                ids.add(int(args[0]))
            except (TypeError, ValueError):
                continue
    return ids
