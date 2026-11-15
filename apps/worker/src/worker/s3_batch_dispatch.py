"""Sliding-window dispatch of S3 batch items: ordering, the Redis pending list, and refills."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

from backfield_db import AgateProcessedItem, AgateRun
from celery import chord, group
from sqlalchemy import func
from sqlmodel import Session, select

from worker.s3_batch_intake import IntakeRamp

logger = logging.getLogger(__name__)


def parent_run_status(session: Session, run_id: str) -> str | None:
    return session.exec(select(AgateRun.status).where(AgateRun.id == run_id)).first()


def order_batch_item_ids_by_text_length(pending: list[tuple[int, int]]) -> list[int]:
    """Return processed-item ids interleaved longest/shortest by article text length.

    Avoids front-loading only the heaviest articles into the initial in-flight window, which
    stacks fleet geocoder/persist contention and synchronizes soft-timeouts.
    """
    if not pending:
        return []
    by_len = sorted(pending, key=lambda row: row[1], reverse=True)
    ordered: list[int] = []
    left = 0
    right = len(by_len) - 1
    take_long = True
    while left <= right:
        if take_long:
            ordered.append(by_len[left][0])
            left += 1
        else:
            ordered.append(by_len[right][0])
            right -= 1
        take_long = not take_long
    return ordered


def batch_max_inflight() -> int:
    """Max concurrent processed-item tasks for a batch (0 = unlimited)."""
    raw = os.getenv("S3_BATCH_MAX_INFLIGHT", "100")
    try:
        return max(0, int(raw.strip()))
    except ValueError:
        return 100


def _batch_pending_redis_key(run_id: str) -> str:
    return f"backfield:batch:{run_id}:pending"


@lru_cache(maxsize=4)
def _redis_client_for_url(url: str) -> Any:
    import redis

    return redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)


def _redis_client_or_none() -> Any | None:
    """Shared Redis client for the pending list (one connection pool per process)."""
    try:
        return _redis_client_for_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    except Exception:
        logger.warning("Batch inflight Redis client unavailable")
        return None


def store_batch_pending_ids(run_id: str, item_ids: list[int]) -> bool:
    """Persist remaining item ids for sliding-window dispatch. False = caller should not cap."""
    client = _redis_client_or_none()
    if client is None:
        return False
    key = _batch_pending_redis_key(run_id)
    try:
        pipe = client.pipeline()
        pipe.delete(key)
        if item_ids:
            pipe.rpush(key, *[str(item_id) for item_id in item_ids])
            pipe.expire(key, 60 * 60 * 24)
        pipe.execute()
        return True
    except Exception:
        logger.warning(
            "Failed to store batch pending ids run_id=%s count=%d",
            run_id,
            len(item_ids),
            exc_info=True,
        )
        return False


def _append_batch_pending_ids(run_id: str, item_ids: list[int]) -> bool:
    """Add ids to the tail of the pending list (intake chunks). False = Redis unavailable."""
    client = _redis_client_or_none()
    if client is None:
        return False
    if not item_ids:
        return True
    key = _batch_pending_redis_key(run_id)
    try:
        pipe = client.pipeline()
        pipe.rpush(key, *[str(item_id) for item_id in item_ids])
        pipe.expire(key, 60 * 60 * 24)
        pipe.execute()
        return True
    except Exception:
        logger.warning(
            "Failed to append batch pending ids run_id=%s count=%d",
            run_id,
            len(item_ids),
            exc_info=True,
        )
        return False


def _batch_pending_length(run_id: str) -> int | None:
    """Ids still waiting for a window slot, or None when Redis cannot answer."""
    client = _redis_client_or_none()
    if client is None:
        return None
    try:
        return int(client.llen(_batch_pending_redis_key(run_id)))
    except Exception:
        logger.warning("Failed to read batch pending length run_id=%s", run_id, exc_info=True)
        return None


def _pop_batch_pending_id(run_id: str) -> int | None:
    client = _redis_client_or_none()
    if client is None:
        return None
    try:
        raw = client.lpop(_batch_pending_redis_key(run_id))
    except Exception:
        logger.warning(
            "Failed to pop batch pending id run_id=%s",
            run_id,
            exc_info=True,
        )
        return None
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _requeue_batch_pending_id(run_id: str, item_id: int) -> None:
    """Put an id back on the Redis tail after a failed Celery enqueue."""
    client = _redis_client_or_none()
    if client is None:
        logger.error(
            "Cannot requeue batch pending id run_id=%s item_id=%s; Redis unavailable",
            run_id,
            item_id,
        )
        return
    try:
        key = _batch_pending_redis_key(run_id)
        client.rpush(key, str(item_id))
        client.expire(key, 60 * 60 * 24)
    except Exception:
        logger.error(
            "Failed to requeue batch pending id run_id=%s item_id=%s",
            run_id,
            item_id,
            exc_info=True,
        )


def clear_batch_pending_ids(run_id: str) -> None:
    client = _redis_client_or_none()
    if client is None:
        return
    try:
        client.delete(_batch_pending_redis_key(run_id))
    except Exception:
        logger.debug("Failed to clear batch pending ids run_id=%s", run_id, exc_info=True)


def _enqueue_processed_item(item_id: int, *, countdown_s: int = 0) -> bool:
    """Queue ``execute_processed_item``. Returns False if Celery enqueue failed."""
    # Imported here because ``worker.tasks`` imports this module for its dispatch helpers.
    from worker.tasks import execute_processed_item

    queue = os.environ.get("CELERY_QUEUE", "agate")
    options: dict[str, Any] = {"countdown": countdown_s} if countdown_s > 0 else {}
    try:
        execute_processed_item.apply_async(args=[item_id], queue=queue, **options)
        return True
    except Exception:
        logger.error(
            "Failed to enqueue execute_processed_item item_id=%s",
            item_id,
            exc_info=True,
        )
        return False


def dispatch_next_batch_item(run_id: str) -> None:
    """Start the next queued item so in-flight stays near ``S3_BATCH_MAX_INFLIGHT``."""
    if batch_max_inflight() <= 0:
        return
    next_id = _pop_batch_pending_id(run_id)
    if next_id is None:
        return
    if not _enqueue_processed_item(next_id):
        _requeue_batch_pending_id(run_id, next_id)


def _count_items_by_status(session: Session, run_id: str, status: str) -> int:
    raw = session.exec(
        select(func.count())
        .select_from(AgateProcessedItem)
        .where(
            AgateProcessedItem.run_id == run_id,
            AgateProcessedItem.status == status,
        )
    ).one()
    return int(raw or 0)


def _pending_item_ids_for_run(session: Session, run_id: str, *, limit: int) -> list[int]:
    if limit <= 0:
        return []
    rows = session.exec(
        select(AgateProcessedItem.id)
        .where(
            AgateProcessedItem.run_id == run_id,
            AgateProcessedItem.status == "pending",
        )
        .order_by(AgateProcessedItem.id)
        .limit(limit)
    ).all()
    return [int(item_id) for item_id in rows]


def replenish_batch_window(session: Session, run_id: str) -> int:
    """Recover stranded ``pending`` items when nothing is in flight.

    Normal sliding-window refill is 1:1 via ``dispatch_next_batch_item`` on each
    completion. Filling ``max_inflight - running`` here raced with that path and
    overshot the cap (queued-but-unclaimed items still count as ``pending``).

    Only when ``running == 0`` and work remains do we refill from Redis then DB.
    Claim remains the race guard if a duplicate task arrives.
    """
    max_inflight = batch_max_inflight()
    if max_inflight <= 0:
        return 0
    if parent_run_status(session, run_id) != "running":
        return 0

    running = _count_items_by_status(session, run_id, "running")
    if running > 0:
        return 0

    pending = _count_items_by_status(session, run_id, "pending")
    if pending <= 0:
        return 0

    slots = min(max_inflight, pending)
    enqueued = 0
    for _ in range(slots):
        next_id = _pop_batch_pending_id(run_id)
        if next_id is None:
            break
        if _enqueue_processed_item(next_id):
            enqueued += 1
        else:
            _requeue_batch_pending_id(run_id, next_id)
            break

    remaining_slots = slots - enqueued
    if remaining_slots > 0:
        for item_id in _pending_item_ids_for_run(session, run_id, limit=remaining_slots):
            if _enqueue_processed_item(item_id):
                enqueued += 1
            else:
                break

    if enqueued:
        logger.info(
            "Batch window replenished (stranded) run_id=%s enqueued=%d pending=%d "
            "max_inflight=%d",
            run_id,
            enqueued,
            pending,
            max_inflight,
        )
    return enqueued


def queue_execute_processed_item_chord(run_id: str, ordered_ids: list[int]) -> None:
    """Queue execute_processed_item work with a sliding ``S3_BATCH_MAX_INFLIGHT`` window.

    When the cap is set, only that many tasks are queued initially; each finished item
    pops the next id from Redis so replacements start immediately. Parent finalize still
    runs from ``execute_processed_item`` via ``_finalize_s3_parent_run``. Unlimited mode
    (cap ``0``) keeps a single chord over all ids for the same finalize guarantee.
    """
    if not ordered_ids:
        return
    # Imported here because ``worker.tasks`` imports this module for its dispatch helpers.
    from worker.tasks import execute_processed_item, finalize_s3_parent_run

    queue = os.environ.get("CELERY_QUEUE", "agate")
    max_inflight = batch_max_inflight()
    if max_inflight <= 0 or len(ordered_ids) <= max_inflight:
        header = group(execute_processed_item.s(item_id) for item_id in ordered_ids)
        chord(header, finalize_s3_parent_run.s(run_id)).apply_async(queue=queue)
        return

    initial = ordered_ids[:max_inflight]
    remaining = ordered_ids[max_inflight:]
    if not store_batch_pending_ids(run_id, remaining):
        # Redis unavailable: fall back to unlimited chord rather than stalling the tail.
        header = group(execute_processed_item.s(item_id) for item_id in ordered_ids)
        chord(header, finalize_s3_parent_run.s(run_id)).apply_async(queue=queue)
        return

    logger.info(
        "Batch sliding window run_id=%s inflight=%d queued=%d max_inflight=%d",
        run_id,
        len(initial),
        len(remaining),
        max_inflight,
    )
    group(execute_processed_item.s(item_id) for item_id in initial).apply_async(queue=queue)


def dispatch_intake_chunk(
    session: Session,
    run_id: str,
    chunk_pending: list[tuple[int, int]],
    ramp: IntakeRamp,
) -> None:
    """Queue a freshly committed intake chunk up to the in-flight cap; the rest waits in Redis.

    Ids are appended to the pending list first, then enough are popped to fill the free window
    slots (``S3_BATCH_MAX_INFLIGHT`` minus running and already-queued items). Completions keep
    refilling 1:1 from the same list.
    """
    ordered_ids = order_batch_item_ids_by_text_length(chunk_pending)
    if not ordered_ids:
        return
    if not _append_batch_pending_ids(run_id, ordered_ids):
        logger.error("Batch intake could not store pending ids run_id=%s", run_id)
        return
    undispatched = _batch_pending_length(run_id)
    if undispatched is None:
        return
    running = _count_items_by_status(session, run_id, "running")
    pending_rows = _count_items_by_status(session, run_id, "pending")
    # Pending rows are queued-but-unclaimed items plus ids still waiting in Redis.
    in_flight = running + max(0, pending_rows - undispatched)
    for _ in range(max(0, batch_max_inflight() - in_flight)):
        next_id = _pop_batch_pending_id(run_id)
        if next_id is None:
            break
        if not _enqueue_processed_item(next_id, countdown_s=ramp.next_countdown_s()):
            _requeue_batch_pending_id(run_id, next_id)
            break
