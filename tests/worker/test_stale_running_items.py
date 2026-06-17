"""Stale ``running`` processed-item reclaim after worker loss."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backfield_db import AgateProcessedItem
from worker import tasks as worker_tasks


def test_is_stale_running_item_after_hard_limit() -> None:
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    item = AgateProcessedItem(
        id=1,
        run_id="run-1",
        status="running",
        started_at=now - timedelta(seconds=worker_tasks._STALE_RUNNING_AFTER_S + 1),
    )
    assert worker_tasks._is_stale_running_item(item, now=now)


def test_is_not_stale_while_within_hard_limit() -> None:
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    item = AgateProcessedItem(
        id=1,
        run_id="run-1",
        status="running",
        started_at=now - timedelta(seconds=60),
    )
    assert not worker_tasks._is_stale_running_item(item, now=now)


def test_item_blocks_finalization_only_for_active_running() -> None:
    now = datetime.now(UTC)
    active = AgateProcessedItem(
        id=1,
        run_id="run-1",
        status="running",
        started_at=now - timedelta(seconds=30),
    )
    stale = AgateProcessedItem(
        id=2,
        run_id="run-1",
        status="running",
        started_at=now - timedelta(seconds=worker_tasks._STALE_RUNNING_AFTER_S + 5),
    )
    assert worker_tasks._item_blocks_run_finalization(active)
    assert not worker_tasks._item_blocks_run_finalization(stale)
