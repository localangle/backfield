"""Helpers for ``agate_processed_item`` running-claim lifecycle in the worker."""

from __future__ import annotations

import logging
import os
import time
from datetime import UTC, datetime

from backfield_db import AgateProcessedItem
from sqlalchemy import update
from sqlmodel import Session, select

logger = logging.getLogger(__name__)

_EXECUTE_PROCESSED_ITEM_TASK = "worker.tasks.execute_processed_item"
_ORPHAN_RUNNING_AFTER_S = int(os.getenv("BATCH_ORPHAN_RUNNING_AFTER_S", "120"))
_ORPHAN_RECONCILE_INTERVAL_S = float(os.getenv("BATCH_ORPHAN_RECONCILE_INTERVAL_S", "30"))
_WORKER_CONCURRENCY = int(os.getenv("CELERY_WORKER_CONCURRENCY", "16"))

_orphan_reconcile_last_by_run: dict[str, float] = {}
_UNOBSERVED_STARTED_AT = object()


def _running_claim_is_orphan(
    item_id: int,
    *,
    started_at: datetime | None,
    updated_at: datetime,
    created_at: datetime,
    active_item_ids: set[int],
    now: datetime,
    orphan_after_s: int,
) -> bool:
    if item_id in active_item_ids:
        return False
    touch = started_at or updated_at or created_at
    if touch.tzinfo is None:
        touch = touch.replace(tzinfo=UTC)
    return (now - touch).total_seconds() >= float(orphan_after_s)


def is_orphan_running_item(
    item: AgateProcessedItem,
    *,
    active_item_ids: set[int],
    now: datetime | None = None,
    orphan_after_s: int = _ORPHAN_RUNNING_AFTER_S,
) -> bool:
    if item.status != "running" or item.id is None:
        return False
    now = now or datetime.now(UTC)
    return _running_claim_is_orphan(
        int(item.id),
        started_at=item.started_at,
        updated_at=item.updated_at,
        created_at=item.created_at,
        active_item_ids=active_item_ids,
        now=now,
        orphan_after_s=orphan_after_s,
    )


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


def release_running_claim(
    session: Session,
    item_id: int,
    *,
    observed_started_at: datetime | None | object = _UNOBSERVED_STARTED_AT,
    now: datetime | None = None,
) -> bool:
    """Return a claimed item to ``pending`` so UI counts and retries stay accurate."""
    now = now or datetime.now(UTC)
    filters = [
        AgateProcessedItem.id == item_id,
        AgateProcessedItem.status == "running",
    ]
    if observed_started_at is not _UNOBSERVED_STARTED_AT:
        filters.append(AgateProcessedItem.started_at == observed_started_at)
    result = session.execute(
        update(AgateProcessedItem)
        .where(*filters)
        .values(
            status="pending",
            started_at=None,
            error_message=None,
            updated_at=now,
        )
        .execution_options(synchronize_session="fetch")
    )
    return bool(result.rowcount)


def release_orphan_running_items_for_run(
    session: Session,
    run_id: str,
    *,
    active_item_ids: set[int],
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(UTC)
    rows = list(
        session.exec(
            select(
                AgateProcessedItem.id,
                AgateProcessedItem.started_at,
                AgateProcessedItem.updated_at,
                AgateProcessedItem.created_at,
            ).where(
                AgateProcessedItem.run_id == run_id,
                AgateProcessedItem.status == "running",
            )
        ).all()
    )
    released = 0
    for item_id, started_at, updated_at, created_at in rows:
        if item_id is None:
            continue
        if not _running_claim_is_orphan(
            int(item_id),
            started_at=started_at,
            updated_at=updated_at,
            created_at=created_at,
            active_item_ids=active_item_ids,
            now=now,
            orphan_after_s=_ORPHAN_RUNNING_AFTER_S,
        ):
            continue
        if release_running_claim(
            session,
            int(item_id),
            observed_started_at=started_at,
            now=now,
        ):
            released += 1
            logger.info(
                "Released orphan running processed_item id=%s run_id=%s back to pending",
                item_id,
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
