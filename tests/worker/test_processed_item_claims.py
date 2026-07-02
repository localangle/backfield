"""Orphan ``running`` processed-item claim release."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backfield_db import AgateProcessedItem
from worker import processed_item_claims as claims


def test_is_orphan_running_item_when_not_active_and_old_enough() -> None:
    now = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
    item = AgateProcessedItem(
        id=9,
        run_id="run-1",
        status="running",
        started_at=now - timedelta(seconds=claims._ORPHAN_RUNNING_AFTER_S + 1),
    )
    assert claims.is_orphan_running_item(item, active_item_ids=set(), now=now)


def test_is_not_orphan_when_item_is_actively_executing() -> None:
    now = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
    item = AgateProcessedItem(
        id=9,
        run_id="run-1",
        status="running",
        started_at=now - timedelta(seconds=claims._ORPHAN_RUNNING_AFTER_S + 60),
    )
    assert not claims.is_orphan_running_item(item, active_item_ids={9}, now=now)


def test_release_orphan_running_items_for_run() -> None:
    now = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
    orphan = AgateProcessedItem(
        id=1,
        run_id="run-1",
        status="running",
        started_at=now - timedelta(seconds=claims._ORPHAN_RUNNING_AFTER_S + 5),
    )
    active = AgateProcessedItem(
        id=2,
        run_id="run-1",
        status="running",
        started_at=now - timedelta(seconds=claims._ORPHAN_RUNNING_AFTER_S + 5),
    )

    class _ExecResult:
        def __init__(self, rows: list[AgateProcessedItem]) -> None:
            self._rows = rows

        def all(self) -> list[AgateProcessedItem]:
            return self._rows

    class _Session:
        def __init__(self) -> None:
            self.rows = {1: orphan, 2: active}

        def exec(self, _stmt: object) -> _ExecResult:
            return _ExecResult([orphan, active])

        def get(self, _model: object, item_id: int) -> AgateProcessedItem | None:
            return self.rows.get(item_id)

        def add(self, row: AgateProcessedItem) -> None:
            if row.id is not None:
                self.rows[int(row.id)] = row

    session = _Session()
    released = claims.release_orphan_running_items_for_run(
        session,
        "run-1",
        active_item_ids={2},
        now=now,
    )
    assert released == 1
    assert orphan.status == "pending"
    assert orphan.started_at is None
    assert active.status == "running"
