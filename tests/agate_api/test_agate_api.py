"""Integration-style tests for Agate API without Docker."""

from __future__ import annotations

import json
from collections.abc import Generator
from decimal import Decimal

import pytest
from api.deps import get_session
from api.main import app
from api.routers import runs
from backfield_auth import create_session_token
from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldAiCallRecord,
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldProject,
    BackfieldUser,
    BackfieldWorkspace,
    BackfieldWorkspaceMembership,
    SubstrateArticle,
)
from backfield_stylebook.bootstrap import ensure_default_stylebook_for_organization
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "agate-api-test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(BackfieldOrganization(name="Backfield", slug="default"))
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        yield TestClient(
            app,
            headers={"Authorization": "Bearer backfield-dev"},
        )
    finally:
        app.dependency_overrides.clear()


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_project_estimated_ai_cost_includes_model_breakdown(tmp_path):
    database_path = tmp_path / "agate-project-ai-cost.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(BackfieldOrganization(name="Backfield", slug="default"))
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        client = TestClient(
            app,
            headers={"Authorization": "Bearer backfield-dev"},
        )
        project = client.post(
            "/projects",
            json={"name": "AI Cost Project", "slug": "ai-cost-project"},
        ).json()

        with Session(engine) as s:
            s.add_all(
                [
                    BackfieldAiCallRecord(
                        project_id=project["id"],
                        provider="openai",
                        provider_model_id="gpt-5-mini",
                        status="succeeded",
                        estimated_cost=Decimal("1.20"),
                        currency="USD",
                    ),
                    BackfieldAiCallRecord(
                        project_id=project["id"],
                        provider="openai",
                        provider_model_id="gpt-5-mini",
                        status="succeeded",
                        estimated_cost=Decimal("0.30"),
                        currency="USD",
                    ),
                    BackfieldAiCallRecord(
                        project_id=project["id"],
                        provider="anthropic",
                        provider_model_id="claude-3-7-sonnet",
                        status="succeeded",
                        estimated_cost=Decimal("0.90"),
                        currency="USD",
                        cost_estimate_incomplete=True,
                    ),
                    BackfieldAiCallRecord(
                        project_id=project["id"],
                        provider="openai",
                        provider_model_id="gpt-5-nano",
                        status="succeeded",
                        estimated_cost=Decimal("0.05"),
                        currency="USD",
                    ),
                ]
            )
            s.commit()

        response = client.get(f"/projects/{project['id']}/estimated-ai-cost")

        assert response.status_code == 200
        assert response.json() == {
            "project_id": project["id"],
            "currency": "USD",
            "estimated_total": "2.450000000000",
            "incomplete_estimate": True,
            "attempt_count": 4,
            "model_breakdown": [
                {"provider_model_id": "gpt-5-mini", "estimated_total": "1.500000000000"},
                {"provider_model_id": "claude-3-7-sonnet", "estimated_total": "0.900000000000"},
                {"provider_model_id": "gpt-5-nano", "estimated_total": "0.050000000000"},
            ],
        }
    finally:
        app.dependency_overrides.clear()


def test_projects_require_auth(tmp_path):
    """Unauthenticated requests to protected routes return 401."""
    database_path = tmp_path / "agate-noauth.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(BackfieldOrganization(name="Backfield", slug="default"))
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        anon = TestClient(app)
        assert anon.get("/projects").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_project_graph_and_run_creation(monkeypatch, client: TestClient):
    sent_task: dict[str, object] = {}

    def fake_send_task(name: str, args: list[str], queue: str) -> None:
        sent_task["name"] = name
        sent_task["args"] = args
        sent_task["queue"] = queue

    monkeypatch.setattr(runs.celery_app, "send_task", fake_send_task)

    project_response = client.post("/projects", json={"name": "Smoke Project", "slug": "smoke"})
    assert project_response.status_code == 200
    project = project_response.json()

    graph_response = client.post(
        "/graphs",
        json={
            "name": "Smoke Flow",
            "project_id": project["id"],
            "spec": {
                "name": "smoke_flow",
                "nodes": [
                    {
                        "id": "n1",
                        "type": "TextInput",
                        "params": {"text": "Austin, TX"},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": "n2",
                        "type": "PlaceExtract",
                        "params": {},
                        "position": {"x": 220, "y": 0},
                    },
                    {
                        "id": "n3",
                        "type": "Output",
                        "params": {},
                        "position": {"x": 440, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "n1",
                        "target": "n2",
                        "sourceHandle": "text",
                        "targetHandle": "text",
                    },
                    {
                        "source": "n2",
                        "target": "n3",
                        "sourceHandle": "locations",
                        "targetHandle": "data",
                    },
                ],
            },
        },
    )
    assert graph_response.status_code == 200
    graph = graph_response.json()

    run_response = client.post("/runs", json={"graph_id": graph["id"]})
    assert run_response.status_code == 200
    run = run_response.json()
    assert run["status"] == "pending"
    assert run["total_items"] == 1
    assert run["pending_items"] == 1
    assert run["running_items"] == 0
    assert run["succeeded_items"] == 0
    assert run["failed_items"] == 0
    assert sent_task == {
        "name": "worker.tasks.execute_agate_run",
        "args": [run["id"]],
        "queue": "agate",
    }

    list_response = client.get("/graphs")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_list_runs_includes_processed_item_counts(monkeypatch, tmp_path):
    database_path = tmp_path / "agate-run-list-counts.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(BackfieldOrganization(name="Backfield", slug="default"))
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    monkeypatch.setattr(runs.celery_app, "send_task", lambda *_a, **_k: None)

    try:
        tc = TestClient(
            app,
            headers={"Authorization": "Bearer backfield-dev"},
        )
        project = tc.post("/projects", json={"name": "Run Counts", "slug": "run-counts"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "Batch flow",
                "project_id": project["id"],
                "spec": {
                    "name": "batch",
                    "nodes": [],
                    "edges": [],
                },
            },
        ).json()
        run = tc.post("/runs", json={"graph_id": graph["id"]}).json()

        with Session(engine) as s:
            row = s.get(AgateRun, run["id"])
            assert row is not None
            row.status = "succeeded"
            s.add(row)
            s.add(
                AgateProcessedItem(
                    run_id=run["id"],
                    source_file="a.json",
                    input_json='{"text":"hello"}',
                    status="succeeded",
                    result_json='{"ok":true}',
                )
            )
            s.add(
                AgateProcessedItem(
                    run_id=run["id"],
                    source_file="b.json",
                    input_json='{"text":"world"}',
                    status="failed",
                    error_message="boom",
                )
            )
            s.commit()

        response = tc.get("/runs")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["id"] == run["id"]
        assert body[0]["total_items"] == 2
        assert body[0]["pending_items"] == 0
        assert body[0]["running_items"] == 0
        assert body[0]["succeeded_items"] == 1
        assert body[0]["failed_items"] == 1
    finally:
        app.dependency_overrides.clear()


def test_delete_graph_cleans_up_run_dependencies(monkeypatch, tmp_path):
    database_path = tmp_path / "agate-delete-graph.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(BackfieldOrganization(name="Backfield", slug="default"))
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    monkeypatch.setattr(runs.celery_app, "send_task", lambda *_a, **_k: None)

    try:
        tc = TestClient(
            app,
            headers={"Authorization": "Bearer backfield-dev"},
        )
        project = tc.post("/projects", json={"name": "Delete Graph", "slug": "delete-graph"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "Graph with runs",
                "project_id": project["id"],
                "spec": {
                    "name": "delete_graph_flow",
                    "nodes": [
                        {
                            "id": "n1",
                            "type": "TextInput",
                            "params": {"text": "Hello"},
                            "position": {"x": 0, "y": 0},
                        }
                    ],
                    "edges": [],
                },
            },
        ).json()
        run = tc.post("/runs", json={"graph_id": graph["id"]}).json()
        run_id = run["id"]

        with Session(engine) as s:
            item = AgateProcessedItem(
                run_id=run_id,
                source_file="a.json",
                input_json='{"text":"hello"}',
                status="succeeded",
                result_json='{"ok":true}',
            )
            s.add(item)
            s.flush()
            assert item.id is not None

            call = BackfieldAiCallRecord(
                project_id=project["id"],
                run_id=run_id,
                processed_item_id=item.id,
                provider="openai",
                provider_model_id="gpt-5-nano",
                status="succeeded",
            )
            s.add(call)

            article = SubstrateArticle(
                project_id=project["id"],
                headline="Delete graph smoke article",
                text="Delete graph smoke body",
                source_run_id=run_id,
                source_item_id=item.id,
            )
            s.add(article)
            s.commit()
            s.refresh(call)
            s.refresh(article)
            call_id = call.id
            article_id = article.id
            item_id = item.id

        resp = tc.delete(f"/graphs/{graph['id']}")
        assert resp.status_code == 204

        with Session(engine) as s:
            assert s.get(AgateGraph, graph["id"]) is None
            assert s.get(AgateRun, run_id) is None
            assert s.get(AgateProcessedItem, item_id) is None
            assert s.get(BackfieldAiCallRecord, call_id) is None
            article_row = s.get(SubstrateArticle, article_id)
            assert article_row is not None
            assert article_row.source_run_id is None
            assert article_row.source_item_id is None
    finally:
        app.dependency_overrides.clear()


def test_s3_graph_run_enqueues_batch_setup(monkeypatch, client: TestClient):
    sent_task: dict[str, object] = {}

    def fake_send_task(name: str, args: list[str], queue: str) -> None:
        sent_task["name"] = name
        sent_task["args"] = args
        sent_task["queue"] = queue

    monkeypatch.setattr(runs.celery_app, "send_task", fake_send_task)

    project = client.post("/projects", json={"name": "S3 Project", "slug": "s3-proj"}).json()
    graph = client.post(
        "/graphs",
        json={
            "name": "S3 Flow",
            "project_id": project["id"],
            "spec": {
                "name": "s3_flow",
                "nodes": [
                    {
                        "id": "s3",
                        "type": "S3Input",
                        "params": {"bucket": "b", "folder_path": ""},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": "out",
                        "type": "Output",
                        "params": {},
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "s3",
                        "target": "out",
                        "sourceHandle": "text",
                        "targetHandle": "data",
                    },
                ],
            },
        },
    ).json()
    run = client.post("/runs", json={"graph_id": graph["id"]}).json()
    assert run["status"] == "pending"
    assert sent_task == {
        "name": "worker.tasks.execute_s3_batch_setup",
        "args": [run["id"]],
        "queue": "agate",
    }


def test_get_run_includes_processed_items_array(monkeypatch, client: TestClient):
    def fake_send_task(*_a, **_k):
        pass

    monkeypatch.setattr(runs.celery_app, "send_task", fake_send_task)

    project = client.post("/projects", json={"name": "Runs API", "slug": "runs-api"}).json()
    graph = client.post(
        "/graphs",
        json={
            "name": "Text flow",
            "project_id": project["id"],
            "spec": {
                "name": "t",
                "nodes": [
                    {
                        "id": "n1",
                        "type": "TextInput",
                        "params": {"text": "Hi"},
                        "position": {"x": 0, "y": 0},
                    },
                ],
                "edges": [],
            },
        },
    ).json()
    run = client.post("/runs", json={"graph_id": graph["id"]}).json()
    detail = client.get(f"/runs/{run['id']}")
    assert detail.status_code == 200
    body = detail.json()
    assert body.get("processed_items") == []


def test_get_run_processed_item_not_found(monkeypatch, client: TestClient):
    def fake_send_task(*_a, **_k):
        pass

    monkeypatch.setattr(runs.celery_app, "send_task", fake_send_task)

    project = client.post("/projects", json={"name": "Item 404", "slug": "item-404"}).json()
    graph = client.post(
        "/graphs",
        json={
            "name": "Text flow",
            "project_id": project["id"],
            "spec": {
                "name": "t",
                "nodes": [
                    {
                        "id": "n1",
                        "type": "TextInput",
                        "params": {"text": "Hi"},
                        "position": {"x": 0, "y": 0},
                    },
                ],
                "edges": [],
            },
        },
    ).json()
    run = client.post("/runs", json={"graph_id": graph["id"]}).json()
    assert client.get(f"/runs/{run['id']}/items/99999").status_code == 404


def test_get_run_processed_item_synthetic_whole_run_pending(monkeypatch, client: TestClient):
    """No DB processed-item rows for non-S3 runs; UI still uses route ``/items/1``."""
    monkeypatch.setattr(runs.celery_app, "send_task", lambda *_a, **_k: None)

    project = client.post("/projects", json={"name": "Synth Item", "slug": "synth-item"}).json()
    graph = client.post(
        "/graphs",
        json={
            "name": "Text flow",
            "project_id": project["id"],
            "spec": {
                "name": "t",
                "nodes": [
                    {
                        "id": "n1",
                        "type": "TextInput",
                        "params": {"text": "Hi"},
                        "position": {"x": 0, "y": 0},
                    },
                ],
                "edges": [],
            },
        },
    ).json()
    run = client.post("/runs", json={"graph_id": graph["id"]}).json()
    resp = client.get(f"/runs/{run['id']}/items/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == 1
    assert body["run_id"] == run["id"]
    assert body["status"] == "pending"
    assert body["input"] == {}
    assert body.get("output") is None


def test_get_run_processed_item_synthetic_second_item_404(monkeypatch, client: TestClient):
    monkeypatch.setattr(runs.celery_app, "send_task", lambda *_a, **_k: None)

    project = client.post("/projects", json={"name": "Synth 404", "slug": "synth-404"}).json()
    graph = client.post(
        "/graphs",
        json={
            "name": "Text flow",
            "project_id": project["id"],
            "spec": {"name": "t", "nodes": [], "edges": []},
        },
    ).json()
    run = client.post("/runs", json={"graph_id": graph["id"]}).json()
    assert client.get(f"/runs/{run['id']}/items/2").status_code == 404


def test_rerun_processed_item_resets_row_and_enqueues_task(monkeypatch, tmp_path):
    """Batch ``agate_processed_item`` rows can be re-queued via POST …/rerun."""
    database_path = tmp_path / "agate-rerun.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(BackfieldOrganization(name="Backfield", slug="default"))
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    captured: dict[str, object] = {}

    def capture_send_task(name: str, args: list[int] | None = None, **kwargs: object) -> None:
        captured["name"] = name
        captured["args"] = args
        captured["queue"] = kwargs.get("queue")

    app.dependency_overrides[get_session] = get_test_session
    monkeypatch.setattr(runs.celery_app, "send_task", capture_send_task)

    try:
        tc = TestClient(
            app,
            headers={"Authorization": "Bearer backfield-dev"},
        )
        project = tc.post("/projects", json={"name": "Rerun API", "slug": "rerun-api"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "Batch",
                "project_id": project["id"],
                "spec": {"name": "b", "nodes": [], "edges": []},
            },
        ).json()
        run = tc.post("/runs", json={"graph_id": graph["id"]}).json()
        rid = run["id"]
        with Session(engine) as s:
            row = s.get(AgateRun, rid)
            assert row is not None
            row.status = "succeeded"
            s.add(row)
            item = AgateProcessedItem(
                run_id=rid,
                source_file="a.json",
                input_json='{"text":"hello"}',
                status="succeeded",
                result_json='{"ok":true}',
            )
            s.add(item)
            s.commit()
            s.refresh(item)
            iid = item.id
        assert iid is not None

        resp = tc.post(f"/runs/{rid}/items/{iid}/rerun")
        assert resp.status_code == 200
        body = resp.json()
        assert body["item_id"] == iid
        assert body["run_id"] == rid
        assert body["status"] == "pending"
        assert "re-queued" in body["message"]

        with Session(engine) as s:
            again = s.get(AgateProcessedItem, iid)
            assert again is not None
            assert again.status == "pending"
            assert again.result_json is None
            assert again.error_message is None
            run_row = s.get(AgateRun, rid)
            assert run_row is not None
            assert run_row.status == "running"

        assert captured["name"] == "worker.tasks.execute_processed_item"
        assert captured["args"] == [iid]
        assert captured["queue"] == "agate"
    finally:
        app.dependency_overrides.clear()


def test_rerun_processed_item_404_when_no_such_row(monkeypatch, client: TestClient):
    monkeypatch.setattr(runs.celery_app, "send_task", lambda *_a, **_k: None)

    project = client.post("/projects", json={"name": "Rerun 404", "slug": "rerun-404"}).json()
    graph = client.post(
        "/graphs",
        json={
            "name": "t",
            "project_id": project["id"],
            "spec": {"name": "t", "nodes": [], "edges": []},
        },
    ).json()
    run = client.post("/runs", json={"graph_id": graph["id"]}).json()
    assert client.post(f"/runs/{run['id']}/items/99999/rerun").status_code == 404


def test_get_run_processed_item_synthetic_with_run_result_json(tmp_path, monkeypatch):
    database_path = tmp_path / "agate-synthetic-result.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        s.add(BackfieldOrganization(name="Backfield", slug="default"))
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    monkeypatch.setattr(runs.celery_app, "send_task", lambda *_a, **_k: None)

    try:
        client = TestClient(
            app,
            headers={"Authorization": "Bearer backfield-dev"},
        )
        project = client.post("/projects", json={"name": "Synth OK", "slug": "synth-ok"}).json()
        graph = client.post(
            "/graphs",
            json={
                "name": "JSON flow",
                "project_id": project["id"],
                "spec": {"name": "j", "nodes": [], "edges": []},
            },
        ).json()
        run = client.post("/runs", json={"graph_id": graph["id"]}).json()
        rid = run["id"]
        with Session(engine) as s:
            row = s.get(AgateRun, rid)
            assert row is not None
            row.status = "succeeded"
            row.result_json = json.dumps({"node_a": {"x": 1}})
            s.add(row)
            s.commit()

        resp = client.get(f"/runs/{rid}/items/1")
        assert resp.status_code == 200
        assert resp.json()["node_outputs"]["node_a"]["x"] == 1
    finally:
        app.dependency_overrides.clear()


def test_run_includes_mapbox_api_token_from_project_secrets(monkeypatch, client: TestClient):
    def fake_send_task(*_a, **_k):
        pass

    monkeypatch.setattr(runs.celery_app, "send_task", fake_send_task)
    monkeypatch.setenv("MASTER_ENCRYPTION_KEY", Fernet.generate_key().decode())

    project = client.post("/projects", json={"name": "Mapbox Project", "slug": "mapbox-p"}).json()
    assert (
        client.put(
            f"/projects/{project['id']}/secrets/MAPBOX_API_TOKEN",
            json={"value": "pk.test_mapbox_token"},
        ).status_code
        == 200
    )
    graph = client.post(
        "/graphs",
        json={
            "name": "Empty",
            "project_id": project["id"],
            "spec": {"name": "empty", "nodes": [], "edges": []},
        },
    ).json()
    run = client.post("/runs", json={"graph_id": graph["id"]}).json()
    assert run.get("mapbox_api_token") == "pk.test_mapbox_token"
    assert client.get(f"/runs/{run['id']}").json().get("mapbox_api_token") == "pk.test_mapbox_token"


def test_create_project_with_workspace_id(tmp_path):
    """Project create accepts workspace_id and persists it."""
    database_path = tmp_path / "agate-project-ws.db"
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

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        c = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        r = c.post(
            "/projects",
            json={"name": "WS Project", "slug": "wsproj", "workspace_id": int(ws.id)},
        )
        assert r.status_code == 200
        body = r.json()
        pid = int(body["id"])
        assert body.get("workspace_id") == int(ws.id)
        assert body.get("organization_id") == oid
        assert body.get("workspace_stylebook_id") is None
        assert body.get("workspace_stylebook_name") is None
        assert body.get("workspace_stylebook_slug") is None
        with Session(engine) as s:
            p = s.get(BackfieldProject, pid)
            assert p is not None
            assert p.workspace_id == int(ws.id)
    finally:
        app.dependency_overrides.clear()


def test_create_project_session_member_denied_without_workspace_membership(tmp_path) -> None:
    """Members may only set workspace_id to a workspace they belong to."""
    database_path = tmp_path / "agate-ws-member.db"
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
        ws_a = BackfieldWorkspace(
            organization_id=oid, stylebook_id=sb_id, name="Workspace A", slug="ws-a"
        )
        ws_b = BackfieldWorkspace(
            organization_id=oid, stylebook_id=sb_id, name="Workspace B", slug="ws-b"
        )
        s.add(ws_a)
        s.add(ws_b)
        s.commit()
        s.refresh(ws_a)
        s.refresh(ws_b)
        wid_a = int(ws_a.id)  # type: ignore[arg-type]
        wid_b = int(ws_b.id)  # type: ignore[arg-type]
        user = BackfieldUser(email="mem@example.com", password_hash="unused")
        s.add(user)
        s.commit()
        s.refresh(user)
        uid = int(user.id)  # type: ignore[arg-type]
        s.add(
            BackfieldOrganizationMembership(
                user_id=uid,
                organization_id=oid,
                role="member",
            )
        )
        s.add(BackfieldWorkspaceMembership(user_id=uid, workspace_id=wid_a))
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        token = create_session_token(
            user_id=uid,
            email="mem@example.com",
            projects=[],
            organization_id=oid,
            org_role="member",
        )
        c = TestClient(app, cookies={"session": token})
        denied = c.post(
            "/projects",
            json={"name": "Bad", "slug": "bad-ws", "workspace_id": wid_b},
        )
        assert denied.status_code == 403
        assert "workspace" in denied.json().get("detail", "").lower()

        ok = c.post(
            "/projects",
            json={"name": "Good", "slug": "good-ws", "workspace_id": wid_a},
        )
        assert ok.status_code == 200
        assert ok.json().get("slug") == "good-ws"
    finally:
        app.dependency_overrides.clear()


def test_create_project_session_org_admin_may_use_any_org_workspace(tmp_path) -> None:
    database_path = tmp_path / "agate-ws-admin.db"
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
        ws_b = BackfieldWorkspace(
            organization_id=oid, stylebook_id=sb_id, name="Workspace B", slug="ws-b2"
        )
        s.add(ws_b)
        s.commit()
        s.refresh(ws_b)
        wid_b = int(ws_b.id)  # type: ignore[arg-type]
        user = BackfieldUser(email="admin@example.com", password_hash="unused")
        s.add(user)
        s.commit()
        s.refresh(user)
        uid = int(user.id)  # type: ignore[arg-type]
        s.add(
            BackfieldOrganizationMembership(
                user_id=uid,
                organization_id=oid,
                role="org_admin",
            )
        )
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        token = create_session_token(
            user_id=uid,
            email="admin@example.com",
            projects=[],
            organization_id=oid,
            org_role="org_admin",
        )
        c = TestClient(app, cookies={"session": token})
        r = c.post(
            "/projects",
            json={"name": "AdminProj", "slug": "admin-ws", "workspace_id": wid_b},
        )
        assert r.status_code == 200
        assert r.json().get("slug") == "admin-ws"
    finally:
        app.dependency_overrides.clear()
