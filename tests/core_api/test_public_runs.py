"""Tests for Core API public run trigger routes."""

from __future__ import annotations

import json
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from agate_runtime.run_graph_spec import parse_run_result_payload
from agate_runtime.run_trigger import PUBLIC_ALIAS_PARAM
from agate_runtime.types import GraphSpec, NodeConfig
from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldOrganization,
    BackfieldProject,
    BackfieldPublicIdempotencyRecord,
    BackfieldWorkspace,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from core_api.deps import get_session
from core_api.main import app
from core_api.routers.public.runs import create as public_runs_create
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from tests.core_api.auth_helpers import attach_test_engine, seed_and_login


@pytest.fixture
def public_runs_client(tmp_path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "public-runs-test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        org = BackfieldOrganization(name="Backfield", slug="default")
        s.add(org)
        s.commit()
        s.refresh(org)
        oid = int(org.id)
        sb = ensure_default_stylebook_for_organization(s, oid)
        sb_id = int(sb.id)  # type: ignore[arg-type]
        ws = BackfieldWorkspace(
            organization_id=oid,
            stylebook_id=sb_id,
            name="Default Workspace",
            slug="default",
        )
        s.add(ws)
        s.commit()
        s.refresh(ws)
        s.add(
            BackfieldProject(
                name="General",
                slug="general",
                organization_id=oid,
                workspace_id=int(ws.id),
            )
        )
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        yield attach_test_engine(TestClient(app), engine)
    finally:
        app.dependency_overrides.clear()


def _bootstrap_and_login(client: TestClient) -> None:
    seed_and_login(client, "runs@example.com", "runs-secret-12")


def _service_key_with_trigger(client: TestClient) -> str:
    _bootstrap_and_login(client)
    created = client.post(
        "/v1/projects/1/api-keys",
        json={
            "credential_type": "service",
            "label": "trigger",
            "scopes": ["runs:trigger"],
        },
    )
    assert created.status_code == 200
    return str(created.json()["raw_key"])


def _read_only_key(client: TestClient) -> str:
    _bootstrap_and_login(client)
    created = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": "user", "label": "read"},
    )
    assert created.status_code == 200
    return str(created.json()["raw_key"])


def _seed_public_text_graph(session_factory, *, enabled: bool = True) -> str:
    gen = session_factory()
    session = next(gen)
    try:
        spec = GraphSpec(
            name="flow",
            nodes=[
                NodeConfig(
                    id="n1",
                    type="TextInput",
                    params={"text": "Saved text", PUBLIC_ALIAS_PARAM: "article"},
                ),
                NodeConfig(id="n2", type="Output", params={}),
            ],
            edges=[],
        )
        graph = AgateGraph(
            id="graph-public-text",
            name="Public text flow",
            spec_json=spec.model_dump_json(),
            project_id=1,
            public_run_enabled=enabled,
        )
        session.add(graph)
        session.commit()
        return graph.id
    finally:
        session.close()


def _seed_public_s3_graph(session_factory) -> str:
    gen = session_factory()
    session = next(gen)
    try:
        spec = GraphSpec(
            name="batch",
            nodes=[
                NodeConfig(
                    id="s1",
                    type="S3Input",
                    params={
                        "bucket": "saved-bucket",
                        "folder_path": "saved/",
                        PUBLIC_ALIAS_PARAM: "batch",
                    },
                ),
                NodeConfig(id="n2", type="Output", params={}),
            ],
            edges=[],
        )
        graph = AgateGraph(
            id="graph-public-s3",
            name="Public S3 flow",
            spec_json=spec.model_dump_json(),
            project_id=1,
            public_run_enabled=True,
        )
        session.add(graph)
        session.commit()
        return graph.id
    finally:
        session.close()


@pytest.fixture
def stub_enqueue(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, list[object]]]:
    enqueued: list[tuple[str, list[object]]] = []

    def fake_enqueue(task_name: str, args: list[object]) -> None:
        enqueued.append((task_name, args))

    monkeypatch.setattr(public_runs_create, "enqueue_worker_task", fake_enqueue)
    return enqueued


def test_public_run_requires_runs_trigger_scope(
    public_runs_client: TestClient,
    stub_enqueue: list[tuple[str, list[object]]],
) -> None:
    raw_key = _read_only_key(public_runs_client)
    graph_id = _seed_public_text_graph(app.dependency_overrides[get_session])
    r = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"graph_id": graph_id},
    )
    assert r.status_code == 403
    assert stub_enqueue == []


def test_public_run_rejects_disabled_graph(
    public_runs_client: TestClient,
    stub_enqueue: list[tuple[str, list[object]]],
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    graph_id = _seed_public_text_graph(app.dependency_overrides[get_session], enabled=False)
    r = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"graph_id": graph_id},
    )
    assert r.status_code == 403
    assert "not enabled" in r.json()["error"]["message"].lower()
    assert stub_enqueue == []


def test_public_run_text_override(
    public_runs_client: TestClient,
    stub_enqueue: list[tuple[str, list[object]]],
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    graph_id = _seed_public_text_graph(app.dependency_overrides[get_session])
    r = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={
            "graph_id": graph_id,
            "inputs": {"article": {"text": "API body text"}},
        },
    )
    assert r.status_code == 202
    assert r.headers["location"].endswith(f"/runs/{r.json()['run_id']}")
    assert r.headers["retry-after"] == "2"
    assert "idempotency-replayed" not in r.headers
    body = r.json()
    assert body["status"] == "running"
    assert body["counts"]["total"] == 1
    assert stub_enqueue[0][0] == "worker.tasks.execute_processed_item"

    gen = app.dependency_overrides[get_session]()
    session = next(gen)
    try:
        run = session.exec(select(AgateRun).where(AgateRun.graph_id == graph_id)).first()
        assert run is not None
        item = session.exec(
            select(AgateProcessedItem).where(AgateProcessedItem.run_id == run.id)
        ).first()
        assert item is not None
        assert item.input_json is not None
        assert "API body text" in item.input_json
    finally:
        session.close()


def test_public_run_s3_override_pins_spec(
    public_runs_client: TestClient,
    stub_enqueue: list[tuple[str, list[object]]],
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    graph_id = _seed_public_s3_graph(app.dependency_overrides[get_session])
    r = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={
            "graph_id": graph_id,
            "inputs": {
                "batch": {
                    "bucket": "override-bucket",
                    "prefix": "override/prefix/",
                }
            },
        },
    )
    assert r.status_code == 202
    assert r.json()["status"] == "pending"
    assert stub_enqueue[0][0] == "worker.tasks.execute_s3_batch_setup"

    gen = app.dependency_overrides[get_session]()
    session = next(gen)
    try:
        run = session.exec(select(AgateRun).where(AgateRun.graph_id == graph_id)).first()
        assert run is not None
        payload = parse_run_result_payload(run.result_json)
        snap = json.loads(str(payload["graph_spec_json"]))
        s3_node = next(n for n in snap["nodes"] if n["type"] == "S3Input")
        assert s3_node["params"]["bucket"] == "override-bucket"
        assert s3_node["params"]["folder_path"] == "override/prefix/"
    finally:
        session.close()


def test_public_run_bad_input_returns_400(
    public_runs_client: TestClient,
    stub_enqueue: list[tuple[str, list[object]]],
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    graph_id = _seed_public_text_graph(app.dependency_overrides[get_session])
    r = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={
            "graph_id": graph_id,
            "inputs": {"article": {"text": ""}},
        },
    )
    assert r.status_code == 400
    assert stub_enqueue == []


def test_public_run_get_status(
    public_runs_client: TestClient,
    stub_enqueue: list[tuple[str, list[object]]],
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    graph_id = _seed_public_text_graph(app.dependency_overrides[get_session])
    created = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"graph_id": graph_id},
    )
    run_id = created.json()["run_id"]
    got = public_runs_client.get(
        f"/public/v1/projects/general/runs/{run_id}",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert got.status_code == 200
    assert got.json()["run_id"] == run_id
    assert got.json()["counts"]["total"] == 1
    assert got.headers["retry-after"] == "2"


def test_public_run_get_missing_run_404(
    public_runs_client: TestClient,
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    r = public_runs_client.get(
        "/public/v1/projects/general/runs/no-such-run-id",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert r.status_code == 404


def test_public_run_idempotency_replays_nested_canonical_body(
    public_runs_client: TestClient,
    stub_enqueue: list[tuple[str, list[object]]],
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    graph_id = _seed_public_text_graph(app.dependency_overrides[get_session])
    headers = {
        "Authorization": f"Bearer {raw_key}",
        "Idempotency-Key": "customer-job-123",
    }
    first = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers=headers,
        json={
            "graph_id": graph_id,
            "inputs": {"article": {"text": "Body", "nested": {"b": 2, "a": [1, 2]}}},
        },
    )
    replay = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers=headers,
        json={
            "inputs": {"article": {"nested": {"a": [1, 2], "b": 2}, "text": "Body"}},
            "graph_id": graph_id,
        },
    )

    assert first.status_code == 202
    assert replay.status_code == 202
    assert replay.json()["run_id"] == first.json()["run_id"]
    assert replay.headers["idempotency-replayed"] == "true"
    assert len(stub_enqueue) == 1


def test_public_run_idempotency_conflicts_for_different_body(
    public_runs_client: TestClient,
    stub_enqueue: list[tuple[str, list[object]]],
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    graph_id = _seed_public_text_graph(app.dependency_overrides[get_session])
    headers = {"Authorization": f"Bearer {raw_key}", "Idempotency-Key": "same-key"}
    first = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers=headers,
        json={"graph_id": graph_id, "inputs": {"article": {"text": "First"}}},
    )
    conflict = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers=headers,
        json={"graph_id": graph_id, "inputs": {"article": {"text": "Second"}}},
    )

    assert first.status_code == 202
    assert conflict.status_code == 409
    assert conflict.json()["error"]["details"]["reason"] == "idempotency_key_reused"
    assert len(stub_enqueue) == 1


def test_public_run_rejects_invalid_idempotency_key(
    public_runs_client: TestClient,
    stub_enqueue: list[tuple[str, list[object]]],
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    graph_id = _seed_public_text_graph(app.dependency_overrides[get_session])
    response = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers={"Authorization": f"Bearer {raw_key}", "Idempotency-Key": "contains spaces"},
        json={"graph_id": graph_id},
    )

    assert response.status_code == 422
    assert stub_enqueue == []


def test_public_run_expired_idempotency_key_can_be_reused(
    public_runs_client: TestClient,
    stub_enqueue: list[tuple[str, list[object]]],
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    graph_id = _seed_public_text_graph(app.dependency_overrides[get_session])
    headers = {"Authorization": f"Bearer {raw_key}", "Idempotency-Key": "expiring-key"}
    first = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers=headers,
        json={"graph_id": graph_id, "inputs": {"article": {"text": "First"}}},
    )

    gen = app.dependency_overrides[get_session]()
    session = next(gen)
    try:
        record = session.exec(select(BackfieldPublicIdempotencyRecord)).one()
        record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.add(record)
        session.commit()
    finally:
        session.close()

    second = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers=headers,
        json={"graph_id": graph_id, "inputs": {"article": {"text": "Second"}}},
    )
    assert second.status_code == 202
    assert second.json()["run_id"] != first.json()["run_id"]
    assert len(stub_enqueue) == 2


def test_public_run_idempotency_cleanup_is_bounded_and_removes_random_keys(
    public_runs_client: TestClient,
) -> None:
    del public_runs_client  # Fixture supplies the isolated database/session override.
    now = datetime.now(UTC)
    gen = app.dependency_overrides[get_session]()
    session = next(gen)
    try:
        for index in range(public_runs_create.IDEMPOTENCY_CLEANUP_BATCH_SIZE + 5):
            session.add(
                BackfieldPublicIdempotencyRecord(
                    project_id=1,
                    operation="create_run",
                    idempotency_key=f"expired-random-{index}",
                    request_hash=f"hash-{index}",
                    expires_at=now - timedelta(days=1),
                )
            )
        session.add(
            BackfieldPublicIdempotencyRecord(
                project_id=1,
                operation="create_run",
                idempotency_key="still-active",
                request_hash="active-hash",
                expires_at=now + timedelta(days=1),
            )
        )
        session.commit()

        assert public_runs_create._cleanup_expired_records(session, now=now) == 100
        remaining = session.exec(select(BackfieldPublicIdempotencyRecord)).all()
        assert len(remaining) == 6
        assert sum(public_runs_create._is_expired(row, now) for row in remaining) == 5

        assert public_runs_create._cleanup_expired_records(session, now=now) == 5
        remaining = session.exec(select(BackfieldPublicIdempotencyRecord)).all()
        assert [row.idempotency_key for row in remaining] == ["still-active"]
        assert public_runs_create._cleanup_expired_records(session, now=now) == 0
    finally:
        session.close()


def test_public_run_creation_lazily_cleans_unrelated_expired_keys(
    public_runs_client: TestClient,
    stub_enqueue: list[tuple[str, list[object]]],
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    graph_id = _seed_public_text_graph(app.dependency_overrides[get_session])
    gen = app.dependency_overrides[get_session]()
    session = next(gen)
    try:
        session.add(
            BackfieldPublicIdempotencyRecord(
                project_id=1,
                operation="create_run",
                idempotency_key="unrelated-expired-key",
                request_hash="old-hash",
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
        session.commit()
    finally:
        session.close()

    created = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers={"Authorization": f"Bearer {raw_key}"},
        json={"graph_id": graph_id},
    )

    assert created.status_code == 202
    gen = app.dependency_overrides[get_session]()
    session = next(gen)
    try:
        assert session.exec(select(BackfieldPublicIdempotencyRecord)).first() is None
    finally:
        session.close()
    assert len(stub_enqueue) == 1


def test_public_run_creation_failure_rolls_back_idempotency_reservation(
    public_runs_client: TestClient,
    stub_enqueue: list[tuple[str, list[object]]],
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    graph_id = _seed_public_text_graph(app.dependency_overrides[get_session])
    failed = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers={
            "Authorization": f"Bearer {raw_key}",
            "Idempotency-Key": "invalid-request",
        },
        json={"graph_id": graph_id, "inputs": {"article": {"text": ""}}},
    )
    assert failed.status_code == 400
    assert stub_enqueue == []

    gen = app.dependency_overrides[get_session]()
    session = next(gen)
    try:
        assert session.exec(select(BackfieldPublicIdempotencyRecord)).first() is None
    finally:
        session.close()


def test_public_run_concurrent_idempotency_creates_one_run(
    public_runs_client: TestClient,
    stub_enqueue: list[tuple[str, list[object]]],
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    graph_id = _seed_public_text_graph(app.dependency_overrides[get_session])

    def submit() -> tuple[int, str]:
        response = public_runs_client.post(
            "/public/v1/projects/general/runs",
            headers={
                "Authorization": f"Bearer {raw_key}",
                "Idempotency-Key": "concurrent-request",
            },
            json={"graph_id": graph_id, "inputs": {"article": {"text": "Same"}}},
        )
        return response.status_code, str(response.json()["run_id"])

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: submit(), range(2)))

    assert {status_code for status_code, _ in results} == {202}
    assert len({run_id for _, run_id in results}) == 1
    assert len(stub_enqueue) == 1


def test_public_run_keyed_enqueue_failure_returns_503_and_retries(
    public_runs_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    graph_id = _seed_public_text_graph(app.dependency_overrides[get_session])
    enqueued: list[tuple[str, list[object]]] = []
    fail_once = {"value": True}

    def flaky_enqueue(task_name: str, args: list[object]) -> None:
        if fail_once["value"]:
            fail_once["value"] = False
            raise RuntimeError("broker unavailable")
        enqueued.append((task_name, args))

    monkeypatch.setattr(public_runs_create, "enqueue_worker_task", flaky_enqueue)
    headers = {
        "Authorization": f"Bearer {raw_key}",
        "Idempotency-Key": "retry-after-broker",
    }
    body = {"graph_id": graph_id, "inputs": {"article": {"text": "Retry me"}}}

    first = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers=headers,
        json=body,
    )
    assert first.status_code == 503
    assert first.headers["retry-after"] == "2"
    assert first.json()["error"]["details"]["reason"] == "enqueue_unavailable"
    assert enqueued == []

    gen = app.dependency_overrides[get_session]()
    session = next(gen)
    try:
        record = session.exec(select(BackfieldPublicIdempotencyRecord)).one()
        assert record.run_id is not None
        assert record.enqueue_state == "pending"
        assert record.enqueue_task_name == "worker.tasks.execute_processed_item"
        reserved_run_id = record.run_id
    finally:
        session.close()

    second = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers=headers,
        json=body,
    )
    assert second.status_code == 202
    assert second.json()["run_id"] == reserved_run_id
    assert second.headers["idempotency-replayed"] == "true"
    assert len(enqueued) == 1

    gen = app.dependency_overrides[get_session]()
    session = next(gen)
    try:
        record = session.exec(select(BackfieldPublicIdempotencyRecord)).one()
        assert record.enqueue_state == "published"
        assert record.enqueued_at is not None
    finally:
        session.close()


def test_public_run_keyed_pending_replay_publishes_once(
    public_runs_client: TestClient,
    stub_enqueue: list[tuple[str, list[object]]],
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    graph_id = _seed_public_text_graph(app.dependency_overrides[get_session])
    headers = {
        "Authorization": f"Bearer {raw_key}",
        "Idempotency-Key": "pending-replay",
    }
    body = {"graph_id": graph_id, "inputs": {"article": {"text": "Pending"}}}
    first = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers=headers,
        json=body,
    )
    assert first.status_code == 202
    assert len(stub_enqueue) == 1

    gen = app.dependency_overrides[get_session]()
    session = next(gen)
    try:
        record = session.exec(select(BackfieldPublicIdempotencyRecord)).one()
        record.enqueue_state = "pending"
        record.enqueued_at = None
        record.enqueue_claimed_at = None
        session.add(record)
        session.commit()
    finally:
        session.close()

    replay = public_runs_client.post(
        "/public/v1/projects/general/runs",
        headers=headers,
        json=body,
    )
    assert replay.status_code == 202
    assert replay.json()["run_id"] == first.json()["run_id"]
    assert replay.headers["idempotency-replayed"] == "true"
    assert len(stub_enqueue) == 2
