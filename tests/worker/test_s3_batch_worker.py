"""S3 batch Celery tasks (eager broker, mocked S3 client).

``execute_s3_batch_setup`` queues a ``chord`` of ``execute_processed_item`` tasks;
eager mode runs the group and ``finalize_s3_parent_run`` inline.
"""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from sqlalchemy import event, update
from sqlmodel import Session, SQLModel, create_engine, select
from worker import tasks as worker_tasks


def _spec_with_s3() -> str:
    return json.dumps(
        {
            "name": "s3_flow",
            "nodes": [
                {
                    "id": "s3n",
                    "type": "S3Input",
                    "params": {"bucket": "my-bucket", "folder_path": "p", "max_files": 10},
                },
                {"id": "out", "type": "Output", "params": {}},
            ],
            "edges": [
                {"source": "s3n", "target": "out", "sourceHandle": "text", "targetHandle": "data"},
            ],
        }
    )


class _FakeBody:
    def __init__(self, payload: bytes) -> None:
        self._buf = io.BytesIO(payload)

    def read(self) -> bytes:
        return self._buf.read()


class _FakeS3:
    def list_objects_v2(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "Contents": [
                {
                    "Key": "p/bad.json",
                    "ETag": '"bad-etag"',
                    "Size": 8,
                    "LastModified": datetime(2024, 1, 1, tzinfo=UTC),
                },
                {
                    "Key": "p/good.json",
                    "ETag": '"good-etag"',
                    "Size": 32,
                    "LastModified": datetime(2024, 1, 2, tzinfo=UTC),
                },
            ],
            "IsTruncated": False,
        }

    def get_object(self, **_kwargs: Any) -> dict[str, Any]:
        key = str(_kwargs.get("Key") or "")
        if key.endswith("bad.json"):
            return {"Body": _FakeBody(b"not json")}
        if key.endswith("good.json"):
            return {"Body": _FakeBody(json.dumps({"text": "Batch line."}).encode())}
        raise AssertionError(key)


@pytest.fixture
def batch_engine(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/s3batch.db"
    monkeypatch.setenv("BACKFIELD_DATABASE_URL", url)
    import backfield_db.session as db_session

    db_session._engine = None

    engine = create_engine(url, connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(worker_tasks, "get_engine", lambda: engine)

    worker_tasks.celery_app.conf.task_always_eager = True
    worker_tasks.celery_app.conf.task_eager_propagates = True

    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-s3")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        stylebook = ensure_default_stylebook_for_organization(session, oid)
        workspace = BackfieldWorkspace(
            organization_id=oid,
            stylebook_id=int(stylebook.id),
            name="Workspace",
            slug="s3-worker",
        )
        session.add(workspace)
        session.flush()
        proj = BackfieldProject(
            organization_id=oid,
            workspace_id=int(workspace.id),
            stylebook_id=int(stylebook.id),
            name="P",
            slug="p-s3",
        )
        session.add(proj)
        session.commit()
        session.refresh(proj)
        pid = int(proj.id)  # type: ignore[arg-type]
        graph = AgateGraph(name="G", spec_json=_spec_with_s3(), project_id=pid)
        session.add(graph)
        session.commit()
        session.refresh(graph)
        gid = graph.id

    yield engine, gid

    worker_tasks.celery_app.conf.task_always_eager = False
    worker_tasks.celery_app.conf.task_eager_propagates = False
    db_session._engine = None


def _create_batch_run(
    engine,
    graph_id: str,
    statuses: list[str],
    *,
    result_json: str | None = None,
    started_at: datetime | None = None,
) -> str:
    with Session(engine) as session:
        run = AgateRun(
            graph_id=graph_id,
            status="running",
            result_json=result_json,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = str(run.id)
        for index, status in enumerate(statuses):
            session.add(
                AgateProcessedItem(
                    run_id=run_id,
                    source_file=f"batch/{index}.json",
                    input_json=json.dumps({"large": "x" * 100}),
                    result_json=json.dumps({"large": "y" * 100}),
                    overlay_json=json.dumps({"note": "z" * 100}),
                    reviewed_output_json=json.dumps({"reviewed": True}),
                    status=status,
                    error_message="item failed" if status == "failed" else None,
                    started_at=started_at if status == "running" else None,
                )
            )
        session.commit()
        return run_id


@pytest.mark.parametrize("blocking_status", ["pending", "running"])
def test_finalization_returns_while_items_are_unfinished(
    batch_engine, blocking_status, monkeypatch
):
    engine, graph_id = batch_engine
    run_id = _create_batch_run(
        engine,
        graph_id,
        ["succeeded", blocking_status],
        started_at=datetime.now(UTC),
    )
    # Avoid eager Celery executing replenished pending items during this gate test.
    monkeypatch.setattr(worker_tasks, "_enqueue_processed_item", lambda _item_id: True)
    monkeypatch.setattr(worker_tasks, "_pop_batch_pending_id", lambda _run_id: None)

    with Session(engine) as session:
        worker_tasks._finalize_s3_parent_run(session, run_id)

    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        assert run is not None
        assert run.status == "running"
        assert run.result_json is None


def test_finalization_preserves_metadata_and_is_idempotent(batch_engine):
    engine, graph_id = batch_engine
    run_id = _create_batch_run(
        engine,
        graph_id,
        ["succeeded", "skipped"],
        result_json=json.dumps(
            {
                "s3_batch": {"valid_executed": 1},
                "graph_spec_json": '{"name":"snapshot"}',
            }
        ),
    )

    with Session(engine) as session:
        worker_tasks._finalize_s3_parent_run(session, run_id)

    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        assert run is not None
        first_result = run.result_json
        first_updated_at = run.updated_at
        payload = json.loads(first_result or "{}")
        assert run.status == "succeeded"
        assert run.error_message is None
        assert payload["s3_batch"] == {"valid_executed": 1}
        assert payload["graph_spec_json"] == '{"name":"snapshot"}'
        assert [item["id"] for item in payload["items"]] == sorted(
            item["id"] for item in payload["items"]
        )

        worker_tasks._finalize_s3_parent_run(session, run_id)
        session.refresh(run)
        assert run.result_json == first_result
        assert run.updated_at == first_updated_at


def test_attention_rollup_yields_to_any_failure(batch_engine):
    engine, graph_id = batch_engine
    attention_run_id = _create_batch_run(engine, graph_id, ["succeeded", "needs_attention"])
    mixed_run_id = _create_batch_run(engine, graph_id, ["needs_attention", "failed"])

    with Session(engine) as session:
        worker_tasks._finalize_s3_parent_run(session, attention_run_id)
        worker_tasks._finalize_s3_parent_run(session, mixed_run_id)

    with Session(engine) as session:
        attention_run = session.get(AgateRun, attention_run_id)
        mixed_run = session.get(AgateRun, mixed_run_id)
        assert attention_run is not None
        assert mixed_run is not None
        assert attention_run.status == "needs_attention"
        assert attention_run.error_message is None
        assert mixed_run.status == "failed"
        assert mixed_run.error_message == "1 of 2 file task(s) failed."


def test_failed_and_stale_items_fail_parent(batch_engine):
    engine, graph_id = batch_engine
    failed_run_id = _create_batch_run(engine, graph_id, ["succeeded", "failed"])
    stale_run_id = _create_batch_run(
        engine,
        graph_id,
        ["running"],
        started_at=datetime.now(UTC) - timedelta(seconds=worker_tasks._STALE_RUNNING_AFTER_S + 5),
    )

    with Session(engine) as session:
        worker_tasks._finalize_s3_parent_run(session, failed_run_id)
        worker_tasks._finalize_s3_parent_run(session, stale_run_id)

    with Session(engine) as session:
        failed_run = session.get(AgateRun, failed_run_id)
        stale_run = session.get(AgateRun, stale_run_id)
        assert failed_run is not None
        assert stale_run is not None
        assert failed_run.status == "failed"
        assert failed_run.error_message == "1 of 2 file task(s) failed."
        assert stale_run.status == "failed"
        assert stale_run.error_message == "1 of 1 file task(s) failed."
        stale_item = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == stale_run_id)
        ).one()
        assert stale_item.error_message == worker_tasks._STALE_RUNNING_MESSAGE


def test_finalization_does_not_overwrite_cancelled_parent(batch_engine):
    engine, graph_id = batch_engine
    run_id = _create_batch_run(
        engine,
        graph_id,
        ["failed"],
        result_json=json.dumps({"s3_batch": {"total_json_objects": 1}}),
    )
    cancelled_at = datetime.now(UTC) - timedelta(seconds=30)
    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        assert run is not None
        run.status = "failed"
        run.error_message = worker_tasks._RUN_CANCELLED_MESSAGE
        run.updated_at = cancelled_at
        session.add(run)
        session.commit()

        worker_tasks._finalize_s3_parent_run(session, run_id)
        session.refresh(run)
        assert run.status == "failed"
        assert run.error_message == worker_tasks._RUN_CANCELLED_MESSAGE
        assert run.result_json == json.dumps({"s3_batch": {"total_json_objects": 1}})
        assert run.updated_at == cancelled_at.replace(tzinfo=None)


def test_repeated_active_finalization_uses_bounded_narrow_queries(
    batch_engine, monkeypatch
):
    engine, graph_id = batch_engine
    item_count = 1000
    run_id = _create_batch_run(engine, graph_id, ["pending"] * item_count)
    statements: list[str] = []
    # Replenish is covered elsewhere; keep this test focused on unfinished-gate query shape.
    monkeypatch.setattr(worker_tasks, "_replenish_batch_window", lambda *_a, **_k: 0)

    def capture_sql(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(str(statement).lower())

    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        with Session(engine) as session:
            for _ in range(25):
                worker_tasks._finalize_s3_parent_run(session, run_id)

            preterminal_item_selects = [
                statement
                for statement in statements
                if statement.lstrip().startswith("select")
                and "from agate_processed_item" in statement
            ]
            assert len(preterminal_item_selects) == 25
            assert all("limit" in statement for statement in preterminal_item_selects)
            assert all("source_file" not in statement for statement in preterminal_item_selects)
            for forbidden in (
                "input_json",
                "result_json",
                "overlay_json",
                "reviewed_output_json",
            ):
                assert all(forbidden not in statement for statement in preterminal_item_selects)

            session.execute(
                update(AgateProcessedItem)
                .where(AgateProcessedItem.run_id == run_id)
                .values(status="succeeded")
            )
            session.commit()
            worker_tasks._finalize_s3_parent_run(session, run_id)
            worker_tasks._finalize_s3_parent_run(session, run_id)
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)

    summary_selects = [
        statement
        for statement in statements
        if statement.lstrip().startswith("select")
        and "from agate_processed_item" in statement
        and "source_file" in statement
    ]
    assert len(summary_selects) == 1
    for forbidden in (
        "input_json",
        "result_json",
        "overlay_json",
        "reviewed_output_json",
    ):
        assert forbidden not in summary_selects[0]


def test_order_batch_item_ids_interleaves_longest_and_shortest() -> None:
    pending = [
        (1, 100),
        (2, 50),
        (3, 200),
        (4, 10),
        (5, 150),
    ]
    assert worker_tasks.order_batch_item_ids_by_text_length(pending) == [3, 4, 5, 2, 1]
    assert worker_tasks.order_batch_item_ids_by_text_length([]) == []
    assert worker_tasks.order_batch_item_ids_by_text_length([(9, 1)]) == [9]


def test_batch_max_inflight_defaults_to_100(monkeypatch) -> None:
    monkeypatch.delenv("S3_BATCH_MAX_INFLIGHT", raising=False)
    assert worker_tasks.batch_max_inflight() == 100
    monkeypatch.setenv("S3_BATCH_MAX_INFLIGHT", "0")
    assert worker_tasks.batch_max_inflight() == 0


def test_queue_execute_processed_item_chord_uses_sliding_window(monkeypatch) -> None:
    group_calls: list[object] = []
    chord_calls: list[object] = []
    stored: list[tuple[str, list[int]]] = []

    class _FakeGroup:
        def __init__(self, tasks: object) -> None:
            self.tasks = list(tasks)  # type: ignore[arg-type]
            group_calls.append(self.tasks)

        def apply_async(self, **_kwargs: object) -> None:
            return None

    class _FakeChord:
        def __init__(self, header: object, body: object) -> None:
            chord_calls.append(body)

        def apply_async(self, **_kwargs: object) -> None:
            return None

    monkeypatch.setenv("S3_BATCH_MAX_INFLIGHT", "2")
    monkeypatch.setattr(worker_tasks, "group", _FakeGroup)
    monkeypatch.setattr(worker_tasks, "chord", _FakeChord)
    monkeypatch.setattr(
        worker_tasks,
        "execute_processed_item",
        SimpleNamespace(s=lambda item_id: ("exec", item_id)),
    )
    monkeypatch.setattr(
        worker_tasks,
        "finalize_s3_parent_run",
        SimpleNamespace(s=lambda run_id: ("finalize", run_id)),
    )
    monkeypatch.setattr(
        worker_tasks,
        "_store_batch_pending_ids",
        lambda run_id, ids: stored.append((run_id, list(ids))) or True,
    )

    worker_tasks.queue_execute_processed_item_chord("run-1", [1, 2, 3, 4])
    assert stored == [("run-1", [3, 4])]
    assert group_calls == [[("exec", 1), ("exec", 2)]]
    assert chord_calls == []

    group_calls.clear()
    stored.clear()
    monkeypatch.setenv("S3_BATCH_MAX_INFLIGHT", "0")
    worker_tasks.queue_execute_processed_item_chord("run-1", [1, 2, 3])
    assert stored == []
    assert len(chord_calls) == 1
    assert chord_calls[0] == ("finalize", "run-1")


def test_dispatch_next_batch_item_applies_async(monkeypatch) -> None:
    applied: list[object] = []
    monkeypatch.setattr(worker_tasks, "_pop_batch_pending_id", lambda _run_id: 99)
    monkeypatch.setattr(
        worker_tasks,
        "execute_processed_item",
        SimpleNamespace(
            apply_async=lambda **kwargs: applied.append(kwargs)  # type: ignore[misc]
        ),
    )
    worker_tasks._dispatch_next_batch_item("run-1")
    assert applied == [{"args": [99], "queue": "agate"}]


def test_dispatch_next_batch_item_requeues_on_enqueue_failure(monkeypatch) -> None:
    requeued: list[tuple[str, int]] = []

    def _fail_enqueue(_item_id: int) -> bool:
        return False

    monkeypatch.setattr(worker_tasks, "_pop_batch_pending_id", lambda _run_id: 42)
    monkeypatch.setattr(worker_tasks, "_enqueue_processed_item", _fail_enqueue)
    monkeypatch.setattr(
        worker_tasks,
        "_requeue_batch_pending_id",
        lambda run_id, item_id: requeued.append((run_id, item_id)),
    )
    worker_tasks._dispatch_next_batch_item("run-1")
    assert requeued == [("run-1", 42)]


def test_replenish_batch_window_stranded_prefers_redis_then_db(
    batch_engine, monkeypatch
) -> None:
    engine, graph_id = batch_engine
    run_id = _create_batch_run(
        engine,
        graph_id,
        ["pending", "pending", "pending"],
    )
    popped = {"n": 0}
    enqueued: list[int] = []

    def _pop(_run_id: str) -> int | None:
        popped["n"] += 1
        if popped["n"] == 1:
            return 9001
        return None

    monkeypatch.setenv("S3_BATCH_MAX_INFLIGHT", "2")
    monkeypatch.setattr(worker_tasks, "_pop_batch_pending_id", _pop)
    monkeypatch.setattr(
        worker_tasks,
        "_enqueue_processed_item",
        lambda item_id: enqueued.append(item_id) or True,
    )

    with Session(engine) as session:
        count = worker_tasks._replenish_batch_window(session, run_id)

    assert count == 2
    assert enqueued[0] == 9001
    # Second slot filled from oldest DB pending (first created item).
    assert len(enqueued) == 2
    assert enqueued[1] != 9001


def test_replenish_batch_window_noop_while_items_running(
    batch_engine, monkeypatch
) -> None:
    engine, graph_id = batch_engine
    run_id = _create_batch_run(
        engine,
        graph_id,
        ["running", "pending", "pending"],
        started_at=datetime.now(UTC),
    )
    enqueued: list[int] = []
    monkeypatch.setenv("S3_BATCH_MAX_INFLIGHT", "2")
    monkeypatch.setattr(
        worker_tasks,
        "_pop_batch_pending_id",
        lambda _run_id: 9001,
    )
    monkeypatch.setattr(
        worker_tasks,
        "_enqueue_processed_item",
        lambda item_id: enqueued.append(item_id) or True,
    )

    with Session(engine) as session:
        count = worker_tasks._replenish_batch_window(session, run_id)

    assert count == 0
    assert enqueued == []


def test_finalize_replenishes_when_items_still_pending(batch_engine, monkeypatch) -> None:
    engine, graph_id = batch_engine
    run_id = _create_batch_run(
        engine,
        graph_id,
        ["succeeded", "pending"],
    )
    calls: list[str] = []

    monkeypatch.setattr(
        worker_tasks,
        "_replenish_batch_window",
        lambda session, rid: calls.append(rid) or 1,
    )

    with Session(engine) as session:
        worker_tasks._finalize_s3_parent_run(session, run_id)

    assert calls == [run_id]
    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        assert run is not None
        assert run.status == "running"


def test_execute_s3_batch_setup_fanout_and_finalize(batch_engine, monkeypatch):
    engine, graph_id = batch_engine

    def _fake_s3() -> _FakeS3:
        return _FakeS3()

    monkeypatch.setattr(worker_tasks, "_s3_client_from_env", _fake_s3)

    def _stub_execute_graph(spec, node_runners=None, *, before_each_node=None, **kwargs):  # noqa: ARG001
        return {"s3_input": {"text": "stub"}}

    monkeypatch.setattr(worker_tasks, "execute_graph", _stub_execute_graph)

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "sk")

    with Session(engine) as session:
        run = AgateRun(graph_id=graph_id, status="pending")
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = run.id

    worker_tasks.execute_s3_batch_setup(run_id)

    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        assert run is not None
        assert run.status == "succeeded"
        graph = session.get(AgateGraph, graph_id)
        assert graph is not None
        items = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == run_id)
        ).all()
        assert len(items) == 1
        assert items[0].status == "succeeded"
        assert items[0].ingestion_ledger_id
        summary = json.loads(run.result_json or "{}")
        assert "items" in summary
        assert summary.get("s3_batch", {}).get("valid_executed") == 1
        assert summary.get("s3_batch", {}).get("skipped_invalid") == 1
        assert summary.get("graph_spec_json") == graph.spec_json
        params = json.loads(graph.spec_json)["nodes"][0]["params"]
        assert params.get("source_id")


def test_s3_setup_rolls_back_items_if_run_is_cancelled_during_listing(
    batch_engine,
    monkeypatch,
):
    engine, graph_id = batch_engine
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "sk")

    with Session(engine) as session:
        run = AgateRun(graph_id=graph_id, status="pending")
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = str(run.id)

    class _CancellingS3(_FakeS3):
        cancelled = False

        def get_object(self, **kwargs: Any) -> dict[str, Any]:
            if not self.cancelled:
                self.cancelled = True
                with Session(engine) as cancel_session:
                    run = cancel_session.get(AgateRun, run_id)
                    assert run is not None
                    run.status = "failed"
                    run.error_message = worker_tasks._RUN_CANCELLED_MESSAGE
                    run.updated_at = datetime.now(UTC)
                    cancel_session.add(run)
                    cancel_session.commit()
            return super().get_object(**kwargs)

    monkeypatch.setattr(worker_tasks, "_s3_client_from_env", _CancellingS3)
    monkeypatch.setattr(
        worker_tasks,
        "chord",
        lambda *_args, **_kwargs: pytest.fail("cancelled setup must not queue item work"),
    )

    worker_tasks.execute_s3_batch_setup(run_id)

    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        assert run is not None
        assert run.status == "failed"
        assert run.error_message == worker_tasks._RUN_CANCELLED_MESSAGE
        items = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == run_id)
        ).all()
        assert list(items) == []


def test_execute_run_replay_setup_clones_items(batch_engine, monkeypatch):
    engine, graph_id = batch_engine

    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "ak")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "sk")

    def _fake_s3() -> _FakeS3:
        return _FakeS3()

    monkeypatch.setattr(worker_tasks, "_s3_client_from_env", _fake_s3)

    def _stub_execute_graph(spec, node_runners=None, *, before_each_node=None, **kwargs):  # noqa: ARG001
        return {"s3_input": {"text": "stub"}}

    monkeypatch.setattr(worker_tasks, "execute_graph", _stub_execute_graph)

    with Session(engine) as session:
        source = AgateRun(graph_id=graph_id, status="pending")
        session.add(source)
        session.commit()
        session.refresh(source)
        source_id = source.id

    worker_tasks.execute_s3_batch_setup(source_id)

    with Session(engine) as session:
        source = session.get(AgateRun, source_id)
        assert source is not None
        source_items = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == source_id)
        ).all()
        replayable = [row for row in source_items if row.input_json and row.status != "skipped"]
        assert replayable
        expected_source_files = {row.source_file for row in replayable}

        new_run = AgateRun(graph_id=graph_id, status="pending")
        new_run.result_json = source.result_json
        session.add(new_run)
        session.commit()
        session.refresh(new_run)
        new_id = new_run.id

    worker_tasks.execute_run_replay_setup(source_id, new_id)

    with Session(engine) as session:
        new_run = session.get(AgateRun, new_id)
        assert new_run is not None
        assert new_run.status == "succeeded"
        cloned = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == new_id)
        ).all()
        assert len(cloned) == len(replayable)
        assert {row.source_file for row in cloned} == expected_source_files
        assert json.loads(new_run.result_json or "{}").get("graph_spec_json")
