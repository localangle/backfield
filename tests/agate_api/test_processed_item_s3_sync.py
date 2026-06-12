"""``POST /runs/{run_id}/items/{item_id}/s3-sync`` — queue an S3 Output re-sync."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from api.deps import get_session
from api.main import app
from api.routers import runs
from backfield_db import AgateProcessedItem, BackfieldOrganization
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from tests.agate_api.test_agate_api import _insert_pending_run, _minimal_text_input_spec


def _s3_output_result_json() -> str:
    return json.dumps(
        {
            "s3_input": {"text": "Hello", "source_file": "in/2026-06-01/story.json"},
            "s3_output": {
                "consolidated": {"text": "Hello"},
                "s3_bucket": "out-bucket",
                "s3_key": "out/2026-06-01/story-output.json",
            },
        }
    )


def _setup_client(tmp_path, monkeypatch, db_name: str):
    engine = create_engine(
        f"sqlite:///{tmp_path / db_name}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(BackfieldOrganization(name="Backfield", slug="default"))
        session.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session

    sent_tasks: list[tuple[str, list[Any]]] = []

    def _capture_send_task(name: str, args=None, **_kwargs: Any) -> None:
        sent_tasks.append((name, list(args or [])))

    monkeypatch.setattr(runs.celery_app, "send_task", _capture_send_task)
    tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
    return engine, tc, sent_tasks


def _insert_succeeded_item(
    engine,
    tc: TestClient,
    *,
    result_json: str | None,
    status: str = "succeeded",
) -> tuple[str, int]:
    project = tc.post("/projects", json={"name": "S3 Sync", "slug": "s3-sync-api"}).json()
    graph = tc.post(
        "/graphs",
        json={
            "name": "Batch",
            "project_id": project["id"],
            "spec": _minimal_text_input_spec(name="s3-sync"),
        },
    ).json()
    with Session(engine) as session:
        run_row = _insert_pending_run(session, graph["id"])
        rid = run_row.id
        run_row.status = "succeeded"
        session.add(run_row)
        item = AgateProcessedItem(
            run_id=rid,
            source_file="in/2026-06-01/story.json",
            input_json="{}",
            status=status,
            result_json=result_json,
        )
        session.add(item)
        session.commit()
        session.refresh(item)
        return rid, int(item.id)  # type: ignore[arg-type]


def test_s3_sync_queues_worker_task(tmp_path, monkeypatch) -> None:
    engine, tc, sent_tasks = _setup_client(tmp_path, monkeypatch, "s3-sync-ok.db")
    try:
        rid, iid = _insert_succeeded_item(engine, tc, result_json=_s3_output_result_json())
        response = tc.post(f"/runs/{rid}/items/{iid}/s3-sync")
        assert response.status_code == 200
        payload = response.json()
        assert payload["item_id"] == iid
        assert payload["run_id"] == rid
        assert (
            "worker.tasks.sync_processed_item_s3_output",
            [iid],
        ) in sent_tasks
    finally:
        app.dependency_overrides.clear()


def test_s3_sync_rejects_item_without_s3_output(tmp_path, monkeypatch) -> None:
    engine, tc, sent_tasks = _setup_client(tmp_path, monkeypatch, "s3-sync-none.db")
    try:
        rid, iid = _insert_succeeded_item(
            engine,
            tc,
            result_json=json.dumps({"json_output": {"consolidated": {"text": "Hi"}}}),
        )
        response = tc.post(f"/runs/{rid}/items/{iid}/s3-sync")
        assert response.status_code == 400
        assert "no S3 Output file" in response.json()["detail"]
        assert all(name != "worker.tasks.sync_processed_item_s3_output" for name, _ in sent_tasks)
    finally:
        app.dependency_overrides.clear()


def test_s3_sync_rejects_incomplete_item(tmp_path, monkeypatch) -> None:
    engine, tc, _sent_tasks = _setup_client(tmp_path, monkeypatch, "s3-sync-pending.db")
    try:
        rid, iid = _insert_succeeded_item(
            engine,
            tc,
            result_json=None,
            status="pending",
        )
        response = tc.post(f"/runs/{rid}/items/{iid}/s3-sync")
        assert response.status_code == 400
        assert "completed story" in response.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_s3_sync_unknown_item_returns_404(tmp_path, monkeypatch) -> None:
    engine, tc, _sent_tasks = _setup_client(tmp_path, monkeypatch, "s3-sync-404.db")
    try:
        rid, _iid = _insert_succeeded_item(engine, tc, result_json=_s3_output_result_json())
        response = tc.post(f"/runs/{rid}/items/999999/s3-sync")
        assert response.status_code == 404
    finally:
        app.dependency_overrides.clear()
