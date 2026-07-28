"""Orphan ``running`` processed-item claim release."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backfield_db import AgateProcessedItem
from sqlalchemy import event, update
from sqlmodel import Session, SQLModel, create_engine
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
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
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

    with Session(engine) as session:
        session.add(orphan)
        session.add(active)
        session.commit()

        released = claims.release_orphan_running_items_for_run(
            session,
            "run-1",
            active_item_ids={2},
            now=now,
        )
        session.commit()
        session.refresh(orphan)
        session.refresh(active)

        assert released == 1
        assert orphan.status == "pending"
        assert orphan.started_at is None
        assert active.status == "running"


def test_release_running_claim_preserves_a_newer_claim() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    observed_started_at = datetime(2026, 7, 1, 12, 0, 0, tzinfo=UTC)
    newer_started_at = observed_started_at + timedelta(minutes=5)

    with Session(engine) as session:
        item = AgateProcessedItem(
            id=1,
            run_id="run-1",
            status="running",
            started_at=observed_started_at,
        )
        session.add(item)
        session.commit()
        session.execute(
            update(AgateProcessedItem)
            .where(AgateProcessedItem.id == 1)
            .values(started_at=newer_started_at)
        )
        session.commit()

        released = claims.release_running_claim(
            session,
            1,
            observed_started_at=observed_started_at,
        )
        session.refresh(item)

        assert not released
        assert item.status == "running"
        assert item.started_at == newer_started_at.replace(tzinfo=None)


def test_orphan_reconciliation_selects_only_claim_columns() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    statements: list[str] = []

    def capture_sql(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        statements.append(str(statement).lower())

    with Session(engine) as session:
        session.add(
            AgateProcessedItem(
                id=1,
                run_id="run-1",
                status="running",
                started_at=datetime.now(UTC),
                input_json='{"large":"input"}',
                result_json='{"large":"result"}',
                overlay_json='{"large":"overlay"}',
                reviewed_output_json='{"large":"reviewed"}',
            )
        )
        session.commit()

    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        with Session(engine) as session:
            claims.release_orphan_running_items_for_run(
                session,
                "run-1",
                active_item_ids={1},
            )
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)

    item_selects = [
        statement
        for statement in statements
        if statement.lstrip().startswith("select")
        and "from agate_processed_item" in statement
    ]
    assert len(item_selects) == 1
    for expected in ("id", "started_at", "updated_at", "created_at"):
        assert expected in item_selects[0]
    for forbidden in (
        "input_json",
        "result_json",
        "overlay_json",
        "reviewed_output_json",
    ):
        assert forbidden not in item_selects[0]
