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


def test_try_claim_reclaims_running_when_redelivery_allowed() -> None:
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    item = AgateProcessedItem(
        id=7,
        run_id="run-1",
        status="running",
        started_at=now - timedelta(seconds=60),
    )

    class _Session:
        def add(self, _row: AgateProcessedItem) -> None:
            return None

    assert worker_tasks._try_claim_processed_item(
        _Session(),
        item,
        allow_running_reclaim=True,
    )
    assert item.error_message is None
    assert item.started_at is not None


def test_try_claim_keeps_active_running_without_redelivery() -> None:
    started = datetime.now(UTC) - timedelta(seconds=60)
    item = AgateProcessedItem(
        id=8,
        run_id="run-1",
        status="running",
        started_at=started,
    )

    class _Session:
        def add(self, _row: AgateProcessedItem) -> None:
            return None

    assert not worker_tasks._try_claim_processed_item(_Session(), item)
    assert item.started_at == started


def test_reap_stale_running_items_for_run_only_affects_stale_rows() -> None:
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    stale = AgateProcessedItem(
        id=1,
        run_id="run-1",
        status="running",
        started_at=now - timedelta(seconds=worker_tasks._STALE_RUNNING_AFTER_S + 5),
    )
    active = AgateProcessedItem(
        id=2,
        run_id="run-1",
        status="running",
        started_at=now - timedelta(seconds=30),
    )
    other_run = AgateProcessedItem(
        id=3,
        run_id="run-2",
        status="running",
        started_at=now - timedelta(seconds=worker_tasks._STALE_RUNNING_AFTER_S + 5),
    )

    class _ExecResult:
        def __init__(self, rows: list[AgateProcessedItem]) -> None:
            self._rows = rows

        def all(self) -> list[AgateProcessedItem]:
            return self._rows

    added: list[AgateProcessedItem] = []

    class _Session:
        def exec(self, _stmt: object) -> _ExecResult:
            return _ExecResult([stale, active])

        def add(self, row: AgateProcessedItem) -> None:
            added.append(row)

    reaped = worker_tasks._reap_stale_running_items_for_run(_Session(), "run-1", now=now)
    assert reaped == 1
    assert stale.status == "failed"
    assert stale.error_message == worker_tasks._STALE_RUNNING_MESSAGE
    assert active.status == "running"
    assert other_run.status == "running"
