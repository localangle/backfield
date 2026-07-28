"""Stale ``running`` processed-item reclaim after worker loss."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from backfield_db import AgateProcessedItem
from sqlmodel import Session, SQLModel, create_engine
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


def test_try_claim_pending_uses_conditional_update() -> None:
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    item = AgateProcessedItem(
        id=7,
        run_id="run-1",
        status="pending",
        started_at=None,
    )
    calls: list[object] = []

    class _Session:
        def execute(self, stmt: object) -> SimpleNamespace:
            calls.append(stmt)
            return SimpleNamespace(rowcount=1)

        def refresh(self, row: AgateProcessedItem) -> None:
            row.status = "running"
            row.started_at = now

    assert worker_tasks._try_claim_processed_item(_Session(), item, now=now)
    assert len(calls) == 1
    assert item.status == "running"


def test_try_claim_reclaims_only_when_stale() -> None:
    now = datetime(2026, 6, 17, 12, 0, 0, tzinfo=UTC)
    started = now - timedelta(seconds=worker_tasks._STALE_RUNNING_AFTER_S + 5)
    item = AgateProcessedItem(
        id=7,
        run_id="run-1",
        status="running",
        started_at=started,
    )
    calls: list[object] = []

    class _Session:
        def execute(self, stmt: object) -> SimpleNamespace:
            calls.append(stmt)
            # First UPDATE is pending claim (miss); second is stale reclaim (hit).
            return SimpleNamespace(rowcount=0 if len(calls) == 1 else 1)

        def refresh(self, row: AgateProcessedItem) -> None:
            if len(calls) >= 2:
                row.started_at = now
                row.error_message = None

    assert worker_tasks._try_claim_processed_item(_Session(), item, now=now)
    assert len(calls) == 2
    assert item.started_at == now


def test_try_claim_keeps_active_running_without_stale_lease() -> None:
    started = datetime.now(UTC) - timedelta(seconds=60)
    item = AgateProcessedItem(
        id=8,
        run_id="run-1",
        status="running",
        started_at=started,
    )
    calls: list[object] = []

    class _Session:
        def execute(self, stmt: object) -> SimpleNamespace:
            calls.append(stmt)
            return SimpleNamespace(rowcount=0)

        def refresh(self, row: AgateProcessedItem) -> None:
            return None

    assert not worker_tasks._try_claim_processed_item(_Session(), item)
    assert item.started_at == started
    assert len(calls) == 1


def test_reap_stale_running_items_for_run_only_affects_stale_rows() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
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

    with Session(engine) as session:
        session.add(stale)
        session.add(active)
        session.add(other_run)
        session.commit()

        reaped = worker_tasks._reap_stale_running_items_for_run(session, "run-1", now=now)
        session.commit()
        session.refresh(stale)
        session.refresh(active)
        session.refresh(other_run)

        assert reaped == 1
        assert stale.status == "failed"
        assert stale.error_message == worker_tasks._STALE_RUNNING_MESSAGE
        assert active.status == "running"
        assert other_run.status == "running"
