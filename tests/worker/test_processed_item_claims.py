"""Orphan ``running`` processed-item claim release."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
)
from celery.exceptions import Retry
from sqlalchemy import event, update
from sqlmodel import Session, SQLModel, create_engine
from worker import processed_item_claims as claims
from worker import tasks as worker_tasks

from tests.project_helpers import project_ownership_fields


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


def test_should_reconcile_when_running_exceeds_concurrency() -> None:
    claims._orphan_reconcile_last_by_run.clear()
    assert claims.should_reconcile_orphan_running_items(
        17,
        run_id="gate-concurrency",
        concurrency=16,
    )


def test_should_reconcile_when_running_exceeds_active_count() -> None:
    claims._orphan_reconcile_last_by_run.clear()
    assert claims.should_reconcile_orphan_running_items(
        5,
        run_id="gate-active",
        concurrency=16,
        active_count=2,
    )


def test_should_not_reconcile_when_within_concurrency_and_active() -> None:
    claims._orphan_reconcile_last_by_run.clear()
    assert not claims.should_reconcile_orphan_running_items(
        5,
        run_id="gate-ok",
        concurrency=16,
        active_count=5,
    )


def test_should_reconcile_keeps_interval_throttle() -> None:
    claims._orphan_reconcile_last_by_run.clear()
    assert claims.should_reconcile_orphan_running_items(
        20,
        run_id="gate-throttle",
        concurrency=16,
        active_count=1,
    )
    assert not claims.should_reconcile_orphan_running_items(
        20,
        run_id="gate-throttle",
        concurrency=16,
        active_count=1,
    )


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


def _text_flow_spec() -> str:
    return json.dumps(
        {
            "name": "claim_collision",
            "nodes": [
                {"id": "t", "type": "TextInput", "params": {"text": "Hello."}},
                {"id": "out", "type": "Output", "params": {}},
            ],
            "edges": [
                {"source": "t", "target": "out", "sourceHandle": "text", "targetHandle": "data"},
            ],
        }
    )


@pytest.fixture
def claim_collision_engine(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/claim_collision.db"
    monkeypatch.setenv("BACKFIELD_DATABASE_URL", url)
    import backfield_db.session as db_session

    db_session._engine = None
    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Backfield", slug="default")
        session.add(org)
        session.commit()
        session.refresh(org)
        ensure_default = __import__(
            "backfield_entities.catalog.bootstrap",
            fromlist=["ensure_default_stylebook_for_organization"],
        ).ensure_default_stylebook_for_organization
        ensure_default(session, organization_id=int(org.id))
        project = BackfieldProject(
            **project_ownership_fields(session, int(org.id)),
            organization_id=int(org.id),
            name="Claims",
            slug="claim-collision",
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        graph = AgateGraph(
            project_id=int(project.id),
            name="flow",
            spec_json=_text_flow_spec(),
        )
        session.add(graph)
        session.commit()
        session.refresh(graph)
        run = AgateRun(graph_id=graph.id, status="running")
        session.add(run)
        session.commit()
        session.refresh(run)
        item = AgateProcessedItem(
            run_id=run.id,
            source_file="inline:text",
            input_json=json.dumps({"text": "Hello."}),
            status="pending",
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        yield engine, int(item.id), run.id
    db_session._engine = None


def _mock_task(*, retries: int = 0) -> MagicMock:
    task = MagicMock()
    task.request = SimpleNamespace(retries=retries, called_directly=False, is_eager=False)

    def _retry(*, countdown: float, **_kwargs: object) -> Retry:
        raise Retry("retry", None, when=countdown)

    task.retry.side_effect = _retry
    return task


def test_claim_miss_releases_orphan_and_reclaims(claim_collision_engine, monkeypatch) -> None:
    engine, item_id, _run_id = claim_collision_engine
    orphan_started = datetime.now(UTC) - timedelta(seconds=claims._ORPHAN_RUNNING_AFTER_S + 30)
    with Session(engine) as session:
        item = session.get(AgateProcessedItem, item_id)
        assert item is not None
        item.status = "running"
        item.started_at = orphan_started
        session.add(item)
        session.commit()

    monkeypatch.setattr(worker_tasks, "active_execute_processed_item_ids", lambda _app: set())
    monkeypatch.setattr(
        worker_tasks,
        "should_reconcile_orphan_running_items",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(worker_tasks, "_reap_stale_running_items_for_run", lambda *_a, **_k: 0)
    monkeypatch.setattr(
        worker_tasks,
        "merge_project_and_org_llm_api_keys",
        lambda *_a, **_k: {},
    )

    task = _mock_task()
    worker_tasks._execute_processed_item_impl(task, item_id)

    task.retry.assert_not_called()
    with Session(engine) as session:
        item = session.get(AgateProcessedItem, item_id)
        assert item is not None
        assert item.status == "succeeded"
        assert item.started_at is not None
        assert item.started_at.replace(tzinfo=UTC) > orphan_started


def test_claim_miss_retries_with_countdown_when_not_orphan(
    claim_collision_engine, monkeypatch
) -> None:
    engine, item_id, _run_id = claim_collision_engine
    with Session(engine) as session:
        item = session.get(AgateProcessedItem, item_id)
        assert item is not None
        item.status = "running"
        item.started_at = datetime.now(UTC) - timedelta(seconds=30)
        session.add(item)
        session.commit()

    monkeypatch.setattr(
        worker_tasks,
        "active_execute_processed_item_ids",
        lambda _app: {item_id},
    )
    monkeypatch.setattr(
        worker_tasks,
        "should_reconcile_orphan_running_items",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(worker_tasks, "_reap_stale_running_items_for_run", lambda *_a, **_k: 0)

    task = _mock_task(retries=1)
    with pytest.raises(Retry) as raised:
        worker_tasks._execute_processed_item_impl(task, item_id)

    expected = worker_tasks._claim_collision_countdown(1)
    assert raised.value.when == expected
    task.retry.assert_called_once()
    assert task.retry.call_args.kwargs["countdown"] == expected

    with Session(engine) as session:
        item = session.get(AgateProcessedItem, item_id)
        assert item is not None
        assert item.status == "running"


def test_claim_collision_countdown_caps() -> None:
    assert worker_tasks._claim_collision_countdown(0) == 5
    assert worker_tasks._claim_collision_countdown(1) == 10
    assert worker_tasks._claim_collision_countdown(2) == 20
    assert worker_tasks._claim_collision_countdown(10) == 60
