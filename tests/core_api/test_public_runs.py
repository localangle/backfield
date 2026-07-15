"""Tests for Core API public run trigger routes."""

from __future__ import annotations

import json
from collections.abc import Generator

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
    assert "not enabled" in r.json()["detail"].lower()
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
    assert r.status_code == 200
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
    assert r.status_code == 200
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


def test_public_run_get_missing_run_404(
    public_runs_client: TestClient,
) -> None:
    raw_key = _service_key_with_trigger(public_runs_client)
    r = public_runs_client.get(
        "/public/v1/projects/general/runs/no-such-run-id",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert r.status_code == 404
