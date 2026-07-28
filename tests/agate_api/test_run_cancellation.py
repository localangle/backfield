"""Large-run cancellation contracts."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import pytest
from api.deps import get_session
from api.main import app
from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
)
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from tests.integration_helpers import patch_test_engine

_CANCELLED = "Run cancelled by user"


@pytest.fixture
def cancel_client(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, Engine, str], None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'run-cancellation.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    patch_test_engine(monkeypatch, engine)

    with Session(engine) as session:
        organization = BackfieldOrganization(name="Cancellation", slug="cancellation")
        session.add(organization)
        session.commit()
        session.refresh(organization)
        project = BackfieldProject(
            organization_id=int(organization.id),
            name="Cancellation",
            slug="cancellation",
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        graph = AgateGraph(
            project_id=int(project.id),
            name="Cancellation",
            spec_json=json.dumps({"name": "cancel", "nodes": [], "edges": []}),
        )
        session.add(graph)
        session.commit()
        session.refresh(graph)
        graph_id = str(graph.id)

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        yield (
            TestClient(app, headers={"Authorization": "Bearer backfield-dev"}),
            engine,
            graph_id,
        )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _insert_run(engine: Engine, graph_id: str, statuses: list[str]) -> str:
    large_payload = json.dumps({"payload": "x" * 10_000})
    with Session(engine) as session:
        run = AgateRun(graph_id=graph_id, status="running")
        session.add(run)
        session.commit()
        session.refresh(run)
        run_id = str(run.id)
        for index, status in enumerate(statuses):
            session.add(
                AgateProcessedItem(
                    run_id=run_id,
                    source_file=f"batch/{index}.json",
                    input_json=large_payload,
                    result_json=large_payload,
                    overlay_json=large_payload,
                    reviewed_output_json=large_payload,
                    status=status,
                    error_message="existing" if status == "failed" else None,
                )
            )
        session.commit()
        return run_id


def _capture_request_sql(
    client: TestClient,
    engine: Engine,
    run_id: str,
) -> tuple[Any, list[str]]:
    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many) -> None:
        statements.append(str(statement).lower())

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.post(f"/runs/{run_id}/cancel")
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    return response, statements


def test_cancel_bulk_updates_active_items_and_returns_compact_status(cancel_client) -> None:
    client, engine, graph_id = cancel_client
    run_id = _insert_run(engine, graph_id, ["pending", "running", "succeeded", "skipped"])

    response, statements = _capture_request_sql(client, engine, run_id)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_message"] == _CANCELLED
    assert body["total_items"] == 4
    assert body["pending_items"] == 0
    assert body["running_items"] == 0
    assert body["succeeded_items"] == 1
    assert body["failed_items"] == 2
    assert "processed_items" not in body
    assert "result" not in body
    assert len(response.content) < 2_000

    with Session(engine) as session:
        items = list(
            session.exec(
                select(AgateProcessedItem)
                .where(AgateProcessedItem.run_id == run_id)
                .order_by(AgateProcessedItem.id)
            ).all()
        )
        assert [(item.status, item.error_message) for item in items] == [
            ("failed", _CANCELLED),
            ("failed", _CANCELLED + " (was running)"),
            ("succeeded", None),
            ("skipped", None),
        ]

    item_updates = [
        statement
        for statement in statements
        if statement.lstrip().startswith("update agate_processed_item")
    ]
    assert len(item_updates) == 1
    for forbidden in (
        "input_json",
        "result_json",
        "overlay_json",
        "reviewed_output_json",
    ):
        assert all(
            forbidden not in statement
            for statement in statements
            if statement.lstrip().startswith("select")
            and "from agate_processed_item" in statement
        )


def test_repeated_cancellation_is_idempotent(cancel_client) -> None:
    client, engine, graph_id = cancel_client
    run_id = _insert_run(engine, graph_id, ["pending", "running"])

    first = client.post(f"/runs/{run_id}/cancel")
    second = client.post(f"/runs/{run_id}/cancel")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == first.json()


def test_cancel_openapi_uses_compact_status_contract(cancel_client) -> None:
    client, _engine, _graph_id = cancel_client

    schema = client.get("/openapi.json").json()
    response_schema = schema["paths"]["/runs/{run_id}/cancel"]["post"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]

    assert response_schema["$ref"].endswith("/RunStatusOut")


def test_cancellation_parent_and_items_roll_back_together(
    cancel_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, engine, graph_id = cancel_client
    run_id = _insert_run(engine, graph_id, ["pending", "running"])

    def fail_commit(_session: Session) -> None:
        raise RuntimeError("forced commit failure")

    monkeypatch.setattr(Session, "commit", fail_commit)
    with pytest.raises(RuntimeError, match="forced commit failure"):
        client.post(f"/runs/{run_id}/cancel")

    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        assert run is not None
        assert run.status == "running"
        assert run.error_message is None
        statuses = session.exec(
            select(AgateProcessedItem.status)
            .where(AgateProcessedItem.run_id == run_id)
            .order_by(AgateProcessedItem.id)
        ).all()
        assert list(statuses) == ["pending", "running"]


def test_cancellation_query_and_response_size_are_bounded(cancel_client) -> None:
    client, engine, graph_id = cancel_client
    small_run_id = _insert_run(engine, graph_id, ["pending"] * 10)
    large_run_id = _insert_run(engine, graph_id, ["pending"] * 1195)

    small_response, small_statements = _capture_request_sql(client, engine, small_run_id)
    large_response, large_statements = _capture_request_sql(client, engine, large_run_id)

    assert small_response.status_code == 200
    assert large_response.status_code == 200
    assert len(large_statements) == len(small_statements)
    assert len(large_response.content) - len(small_response.content) < 100
    assert len(large_response.content) < 2_000
