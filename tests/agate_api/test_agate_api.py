"""Integration-style tests for Agate API without Docker."""

from __future__ import annotations

import hashlib
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
    BackfieldApiCredential,
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldProject,
    BackfieldUser,
    BackfieldWorkspace,
    BackfieldWorkspaceMembership,
    SubstrateArticle,
    SubstratePerson,
    SubstratePersonMention,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from tests.integration_helpers import patch_test_engine


def _minimal_text_input_spec(
    *,
    name: str = "test_flow",
    text: str = "Test article body for API tests.",
) -> dict[str, object]:
    return {
        "name": name,
        "nodes": [
            {"id": "n1", "type": "TextInput", "params": {"text": text}},
            {"id": "out", "type": "Output", "params": {}},
        ],
        "edges": [
            {
                "source": "n1",
                "target": "out",
                "sourceHandle": "text",
                "targetHandle": "data",
            },
        ],
    }


def _insert_pending_run(session: Session, graph_id: str) -> AgateRun:
    """Insert a run without ``POST /runs`` (no auto single-item row)."""
    run = AgateRun(graph_id=graph_id, status="pending")
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "agate-api-test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    patch_test_engine(monkeypatch, engine)

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
    assert response.json() == {"ok": True, "service": "agate-api"}


def test_healthz(client: TestClient):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "service": "agate-api"}


def test_readyz(client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("backfield_auth.service_health.check_redis", lambda redis_url=None: "ok")
    response = client.get("/readyz")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "ok"


def test_version(client: TestClient):
    response = client.get("/version")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "agate-api"
    assert {"version", "git_sha", "build_time"} <= set(body)


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


def test_run_estimated_ai_cost_node_breakdown_includes_node_type(tmp_path):
    database_path = tmp_path / "agate-run-ai-cost.db"
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
            json={"name": "Run AI Cost", "slug": "run-ai-cost"},
        ).json()
        graph = client.post(
            "/graphs",
            json={
                "name": "People flow",
                "project_id": project["id"],
                "spec": {
                    "name": "people_flow",
                    "nodes": [
                        {
                            "id": "n1",
                            "type": "TextInput",
                            "params": {"text": "Hello"},
                            "position": {"x": 0, "y": 0},
                        },
                        {
                            "id": "n2",
                            "type": "PersonExtract",
                            "params": {},
                            "position": {"x": 200, "y": 0},
                        },
                    ],
                    "edges": [],
                },
            },
        ).json()

        with Session(engine) as s:
            run = _insert_pending_run(s, graph["id"])
            s.add(
                BackfieldAiCallRecord(
                    project_id=project["id"],
                    run_id=run.id,
                    node_id="node-0",
                    node_type="PersonExtract",
                    provider="openai",
                    provider_model_id="gpt-5-nano",
                    status="succeeded",
                    estimated_cost=Decimal("0.004"),
                    currency="USD",
                )
            )
            s.commit()
            run_id = run.id

        response = client.get(f"/runs/{run_id}/estimated-ai-cost")

        assert response.status_code == 200
        assert response.json()["node_breakdown"] == [
            {
                "node_id": "node-0",
                "node_type": "PersonExtract",
                "estimated_total": "0.004000000000",
            }
        ]
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


def test_create_run_rejects_graph_without_ingress(client: TestClient):
    project = client.post("/projects", json={"name": "No ingress", "slug": "no-ingress"}).json()
    graph = client.post(
        "/graphs",
        json={
            "name": "Output only",
            "project_id": project["id"],
            "spec": {
                "name": "empty",
                "nodes": [{"id": "out", "type": "Output", "params": {}}],
                "edges": [],
            },
        },
    ).json()
    resp = client.post("/runs", json={"graph_id": graph["id"]})
    assert resp.status_code == 400
    assert "TextInput or JSONInput" in resp.json().get("detail", "")


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
    assert run["status"] == "running"
    assert run["total_items"] == 1
    assert run["pending_items"] == 1
    assert run["running_items"] == 0
    assert run["succeeded_items"] == 0
    assert run["failed_items"] == 0
    assert sent_task["name"] == "worker.tasks.execute_processed_item"
    assert sent_task["queue"] == "agate"
    assert isinstance(sent_task["args"], list)
    assert len(sent_task["args"]) == 1
    item_id = sent_task["args"][0]
    assert len(run["processed_items"]) == 1
    summary = run["processed_items"][0]
    assert summary["id"] == item_id
    assert summary["run_id"] == run["id"]
    assert summary["source_file"] == "inline:text"
    assert summary["input_preview"] == "Austin, TX"
    assert summary["status"] == "pending"

    detail = client.get(f"/runs/{run['id']}/items/{item_id}")
    assert detail.status_code == 200
    assert detail.json().get("synthetic") is False
    assert detail.json()["input"]["text"] == "Austin, TX"

    list_response = client.get("/graphs")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


def test_run_graph_spec_snapshot_and_flow_changed(monkeypatch, client: TestClient):
    monkeypatch.setattr(runs.celery_app, "send_task", lambda *args, **kwargs: None)

    project = client.post("/projects", json={"name": "Snap Project", "slug": "snap-proj"}).json()
    base_spec = {
        "name": "snap_flow",
        "nodes": [
            {
                "id": "n1",
                "type": "TextInput",
                "params": {"text": "Austin, TX"},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "n2",
                "type": "Output",
                "params": {},
                "position": {"x": 220, "y": 0},
            },
        ],
        "edges": [
            {
                "source": "n1",
                "target": "n2",
                "sourceHandle": "text",
                "targetHandle": "data",
            }
        ],
    }
    graph = client.post(
        "/graphs",
        json={"name": "Snap Flow", "project_id": project["id"], "spec": base_spec},
    ).json()

    run = client.post("/runs", json={"graph_id": graph["id"]}).json()
    assert run["graph_spec_snapshot_json"]
    assert run["flow_changed_since_run"] is False

    detail = client.get(f"/runs/{run['id']}").json()
    assert detail["graph_spec_snapshot_json"] == run["graph_spec_snapshot_json"]
    assert detail["flow_changed_since_run"] is False

    changed_spec = {
        **base_spec,
        "nodes": [
            {
                "id": "n1",
                "type": "TextInput",
                "params": {"text": "Chicago, IL"},
                "position": {"x": 0, "y": 0},
            },
            base_spec["nodes"][1],
        ],
    }
    update = client.put(
        f"/graphs/{graph['id']}",
        json={"name": "Snap Flow", "project_id": project["id"], "spec": changed_spec},
    )
    assert update.status_code == 200

    detail_after_change = client.get(f"/runs/{run['id']}").json()
    assert detail_after_change["flow_changed_since_run"] is True


def test_replay_run_uses_source_snapshot_not_live_graph(monkeypatch, client: TestClient):
    sent: dict[str, object] = {}

    def capture_send_task(name: str, args: list[str], queue: str) -> None:
        sent["name"] = name
        sent["args"] = args
        sent["queue"] = queue

    monkeypatch.setattr(runs.celery_app, "send_task", capture_send_task)

    project = client.post(
        "/projects",
        json={"name": "Replay Project", "slug": "replay-proj"},
    ).json()
    base_spec = {
        "name": "replay_flow",
        "nodes": [
            {
                "id": "n1",
                "type": "TextInput",
                "params": {"text": "Austin, TX"},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "n2",
                "type": "Output",
                "params": {},
                "position": {"x": 220, "y": 0},
            },
        ],
        "edges": [
            {
                "source": "n1",
                "target": "n2",
                "sourceHandle": "text",
                "targetHandle": "data",
            }
        ],
    }
    graph = client.post(
        "/graphs",
        json={"name": "Replay Flow", "project_id": project["id"], "spec": base_spec},
    ).json()

    source = client.post("/runs", json={"graph_id": graph["id"]}).json()
    assert "Austin" in (source.get("graph_spec_snapshot_json") or "")

    changed_spec = {
        **base_spec,
        "nodes": [
            {
                "id": "n1",
                "type": "TextInput",
                "params": {"text": "Chicago, IL"},
                "position": {"x": 0, "y": 0},
            },
            base_spec["nodes"][1],
        ],
    }
    update = client.put(
        f"/graphs/{graph['id']}",
        json={"name": "Replay Flow", "project_id": project["id"], "spec": changed_spec},
    )
    assert update.status_code == 200

    replay = client.post(f"/runs/{source['id']}/replay")
    assert replay.status_code == 200
    new_run = replay.json()
    assert "Austin" in (new_run.get("graph_spec_snapshot_json") or "")
    assert "Chicago" not in (new_run.get("graph_spec_snapshot_json") or "")
    assert sent.get("name") == "worker.tasks.execute_run_replay_setup"
    assert sent.get("args") == [source["id"], new_run["id"]]


def test_graph_description_round_trip(client: TestClient):
    project_response = client.post("/projects", json={"name": "Desc Project", "slug": "desc-proj"})
    assert project_response.status_code == 200
    project = project_response.json()

    minimal_spec = {
        "name": "desc_flow",
        "nodes": [
            {
                "id": "n1",
                "type": "TextInput",
                "params": {"text": "Hello"},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "n2",
                "type": "Output",
                "params": {},
                "position": {"x": 220, "y": 0},
            },
        ],
        "edges": [
            {
                "source": "n1",
                "target": "n2",
                "sourceHandle": "text",
                "targetHandle": "data",
            },
        ],
    }

    create_response = client.post(
        "/graphs",
        json={
            "name": "Flow with description",
            "description": "Extracts places from articles",
            "project_id": project["id"],
            "spec": minimal_spec,
        },
    )
    assert create_response.status_code == 200
    graph = create_response.json()
    assert graph["description"] == "Extracts places from articles"

    update_response = client.put(
        f"/graphs/{graph['id']}",
        json={
            "name": graph["name"],
            "description": "Updated description",
            "project_id": project["id"],
            "spec": graph["spec"],
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["description"] == "Updated description"

    get_response = client.get(f"/graphs/{graph['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["description"] == "Updated description"

    list_response = client.get("/graphs")
    assert list_response.status_code == 200
    listed = next(row for row in list_response.json() if row["id"] == graph["id"])
    assert listed["description"] == "Updated description"


def test_project_api_key_scopes_agate_api_access(tmp_path):
    database_path = tmp_path / "agate-project-key-scope.db"
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
        tc = TestClient(
            app,
            headers={"Authorization": "Bearer backfield-dev"},
        )
        project_one = tc.post(
            "/projects",
            json={"name": "Project One", "slug": "project-one"},
        ).json()
        project_two = tc.post(
            "/projects",
            json={"name": "Project Two", "slug": "project-two"},
        ).json()

        raw_key = "bfk_project_scope_test_key_1234567890abcdef"
        with Session(engine) as s:
            s.add(
                BackfieldApiCredential(
                    project_id=project_one["id"],
                    credential_type="service",
                    key_prefix=raw_key[:22],
                    key_hash=hashlib.sha256(raw_key.encode("utf-8")).hexdigest(),
                    label="scope-test",
                )
            )
            s.commit()

        headers = {"Authorization": f"Bearer {raw_key}"}

        listed = tc.get("/projects", headers=headers)
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()] == [project_one["id"]]

        own = tc.get(f"/projects/{project_one['id']}", headers=headers)
        assert own.status_code == 200
        assert own.json()["id"] == project_one["id"]

        other = tc.get(f"/projects/{project_two['id']}", headers=headers)
        assert other.status_code == 403
        assert "project" in other.json().get("detail", "").lower()
    finally:
        app.dependency_overrides.clear()


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
                "spec": {"name": "batch", "nodes": [], "edges": []},
            },
        ).json()

        with Session(engine) as s:
            row = _insert_pending_run(s, graph["id"])
            run = {"id": row.id}
            assert row is not None
            row.status = "succeeded"
            s.add(row)
            s.add(
                AgateProcessedItem(
                    run_id=run["id"],
                    source_file="a.json",
                    input_json='{"text":"hello from a very long manual input payload"}',
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

        detail = tc.get(f"/runs/{run['id']}")
        assert detail.status_code == 200
        processed = detail.json()["processed_items"]
        assert processed[0]["input_preview"] == "hello from a very long manual…"
        assert processed[1]["input_preview"] == "world"
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
        with Session(engine) as s:
            row = _insert_pending_run(s, graph["id"])
            run_id = row.id
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
    assert len(body.get("processed_items") or []) == 1
    assert body["processed_items"][0]["status"] == "pending"


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


def test_get_run_processed_item_synthetic_whole_run_pending(monkeypatch, tmp_path):
    """Legacy runs with no ``agate_processed_item`` rows still expose synthetic ``/items/1``."""
    database_path = tmp_path / "agate-synth-pending.db"
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
        tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        project = tc.post("/projects", json={"name": "Synth Item", "slug": "synth-item"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "Text flow",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="t", text="Hi"),
            },
        ).json()
        with Session(engine) as s:
            run_row = _insert_pending_run(s, graph["id"])
            run = {"id": run_row.id}
        resp = tc.get(f"/runs/{run['id']}/items/1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == 1
        assert body["run_id"] == run["id"]
        assert body["synthetic"] is True
        assert body["status"] == "pending"
        assert body["input"] == {}
        assert body.get("output") is None
        assert body.get("overlay") is None
        assert body.get("overlay_version") == 0
        assert body.get("merged_locations") == []
        assert body.get("stale_overlay_entries") == []
        ac = body["article_context"]
        assert ac["resolution"] == "none"
        assert ac["reason"] == "no_input_article_id"
    finally:
        app.dependency_overrides.clear()


def test_get_run_processed_item_synthetic_second_item_404(monkeypatch, client: TestClient):
    monkeypatch.setattr(runs.celery_app, "send_task", lambda *_a, **_k: None)

    project = client.post("/projects", json={"name": "Synth 404", "slug": "synth-404"}).json()
    graph = client.post(
        "/graphs",
        json={
            "name": "Text flow",
            "project_id": project["id"],
            "spec": _minimal_text_input_spec(name="t", text="Hi"),
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
                "spec": _minimal_text_input_spec(name="b"),
            },
        ).json()
        with Session(engine) as s:
            row = _insert_pending_run(s, graph["id"])
            rid = row.id
            row.status = "succeeded"
            s.add(row)
            item = AgateProcessedItem(
                run_id=rid,
                source_file="a.json",
                input_json='{"text":"hello"}',
                status="succeeded",
                result_json='{"ok":true}',
                overlay_json='{"places":{}}',
                overlay_version=3,
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
            assert again.replace_article_geography_on_persist is False
            assert again.overlay_json is None
            assert again.reviewed_output_json is None
            assert again.overlay_version == 0
            run_row = s.get(AgateRun, rid)
            assert run_row is not None
            assert run_row.status == "running"

        assert captured["name"] == "worker.tasks.execute_processed_item"
        assert captured["args"] == [iid]
        assert captured["queue"] == "agate"
    finally:
        app.dependency_overrides.clear()


def test_rerun_synthetic_whole_graph_run_resets_run_and_enqueues_task(
    monkeypatch, tmp_path
):
    """Whole-graph ``items/1`` reruns via ``execute_agate_run`` when there are no batch rows."""
    database_path = tmp_path / "agate-rerun-synthetic.db"
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

    def capture_send_task(name: str, args: list[str] | None = None, **kwargs: object) -> None:
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
        project = tc.post(
            "/projects", json={"name": "Rerun Synth", "slug": "rerun-synth"}
        ).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "Single",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="s"),
            },
        ).json()
        with Session(engine) as s:
            row = _insert_pending_run(s, graph["id"])
            rid = row.id
            row.status = "succeeded"
            row.result_json = json.dumps({"node_a": {"x": 1}})
            s.add(row)
            s.commit()

        resp = tc.post(f"/runs/{rid}/items/1/rerun")
        assert resp.status_code == 200
        body = resp.json()
        assert body["item_id"] == 1
        assert body["run_id"] == rid
        assert body["status"] == "pending"

        with Session(engine) as s:
            again = s.get(AgateRun, rid)
            assert again is not None
            assert again.status == "pending"
            assert again.result_json is None
            assert again.error_message is None
            assert again.replace_article_geography_on_persist is False

        assert captured["name"] == "worker.tasks.execute_agate_run"
        assert captured["args"] == [rid]
        assert captured["queue"] == "agate"
    finally:
        app.dependency_overrides.clear()


def test_create_run_with_replace_article_geography_flag(monkeypatch, tmp_path):
    database_path = tmp_path / "agate-replace-flag.db"
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

    monkeypatch.setattr(runs.celery_app, "send_task", lambda *_a, **_k: None)
    app.dependency_overrides[get_session] = get_test_session
    try:
        tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        project = tc.post(
            "/projects", json={"name": "Replace flag", "slug": "replace-flag"}
        ).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "t",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="t"),
            },
        ).json()
        run = tc.post(
            "/runs",
            json={
                "graph_id": graph["id"],
                "replace_article_geography_on_persist": True,
            },
        ).json()
        with Session(engine) as s:
            row = s.get(AgateRun, run["id"])
            assert row is not None
            assert row.replace_article_geography_on_persist is True
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
            "spec": _minimal_text_input_spec(name="t"),
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
                "spec": _minimal_text_input_spec(name="j"),
            },
        ).json()
        with Session(engine) as s:
            row = _insert_pending_run(s, graph["id"])
            rid = row.id
            row.status = "succeeded"
            row.result_json = json.dumps({"node_a": {"x": 1}})
            s.add(row)
            s.commit()

        resp = client.get(f"/runs/{rid}/items/1")
        assert resp.status_code == 200
        j = resp.json()
        assert j["synthetic"] is True
        assert j["node_outputs"]["node_a"]["x"] == 1
        assert j.get("overlay") is None
        assert j.get("overlay_version") == 0
        assert j.get("merged_locations") == []
        assert j.get("stale_overlay_entries") == []
        ac = j["article_context"]
        assert ac["resolution"] == "none"
        assert ac["reason"] == "no_input_article_id"
    finally:
        app.dependency_overrides.clear()


def test_patch_processed_item_overlay_success_and_409(tmp_path, monkeypatch):
    database_path = tmp_path / "agate-overlay.db"
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
        tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        project = tc.post("/projects", json={"name": "Overlay API", "slug": "overlay-api"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "Batch",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="b"),
            },
        ).json()
        with Session(engine) as s:
            row = _insert_pending_run(s, graph["id"])
            rid = row.id
            row.status = "succeeded"
            s.add(row)
            item = AgateProcessedItem(
                run_id=rid,
                source_file="a.json",
                input_json='{"text":"hello"}',
                status="succeeded",
                result_json=json.dumps({"ok": True}),
            )
            s.add(item)
            s.commit()
            s.refresh(item)
            iid = item.id
        assert iid is not None

        first = tc.get(f"/runs/{rid}/items/{iid}")
        assert first.status_code == 200
        assert first.json().get("overlay") is None
        assert first.json().get("overlay_version") == 0

        ok = tc.patch(
            f"/runs/{rid}/items/{iid}",
            json={"overlay": {"notes": "a"}},
            headers={"If-Match": '"0"'},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body["overlay_version"] == 1
        assert body["overlay"]["notes"] == "a"
        assert body["output"]["ok"] is True
        ac = body["article_context"]
        assert ac["resolution"] == "inline_fallback"
        assert ac["body"] == "hello"

        conflict = tc.patch(
            f"/runs/{rid}/items/{iid}",
            json={"overlay": {"notes": "b"}},
            headers={"If-Match": '"0"'},
        )
        assert conflict.status_code == 409
        detail = conflict.json()["detail"]
        assert detail["error"] == "overlay_version_conflict"
        assert detail["current_version"] == 1

        ok2 = tc.patch(
            f"/runs/{rid}/items/{iid}",
            json={"overlay": {"notes": "c"}},
            headers={"If-Match": '"1"'},
        )
        assert ok2.status_code == 200
        assert ok2.json()["overlay_version"] == 2
        assert ok2.json()["overlay"]["notes"] == "c"
        assert ok2.json().get("reviewed_output") is None
    finally:
        app.dependency_overrides.clear()


def test_patch_processed_item_overlay_materializes_reviewed_output(tmp_path, monkeypatch):
    database_path = tmp_path / "agate-reviewed-out.db"
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

    result = {
        "geocode_agent": {
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "p1",
                            "description": "orig",
                            "original_text": "t",
                            "location": {"full": "X", "type": "city", "components": {}},
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            }
        }
    }

    try:
        tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        project = tc.post("/projects", json={"name": "Reviewed Out", "slug": "reviewed-out"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "Batch",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="b"),
            },
        ).json()
        with Session(engine) as s:
            row = _insert_pending_run(s, graph["id"])
            rid = row.id
            row.status = "succeeded"
            s.add(row)
            item = AgateProcessedItem(
                run_id=rid,
                source_file="a.json",
                input_json='{"text":"hello"}',
                status="succeeded",
                result_json=json.dumps(result),
            )
            s.add(item)
            s.commit()
            s.refresh(item)
            iid = item.id
        assert iid is not None

        ok = tc.patch(
            f"/runs/{rid}/items/{iid}",
            json={"overlay": {"locations": {"by_anchor": {"p1": {"description": "reviewed"}}}}},
            headers={"If-Match": '"0"'},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body.get("reviewed_output") is not None
        reviewed_places = body["reviewed_output"]["geocode_agent"]["places"]
        assert reviewed_places["areas"]["cities"][0]["description"] == "reviewed"
        model_places = body["output"]["geocode_agent"]["places"]
        assert model_places["areas"]["cities"][0]["description"] == "orig"

        with Session(engine) as s:
            row_item = s.get(AgateProcessedItem, iid)
            assert row_item is not None
            assert row_item.reviewed_output_json is not None
    finally:
        app.dependency_overrides.clear()


def test_patch_processed_item_overlay_geometry_400(tmp_path, monkeypatch):
    database_path = tmp_path / "agate-overlay-geom.db"
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
        tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        project = tc.post("/projects", json={"name": "Geom API", "slug": "geom-api"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "Batch",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="b"),
            },
        ).json()
        with Session(engine) as s:
            row = _insert_pending_run(s, graph["id"])
            rid = row.id
            row.status = "succeeded"
            s.add(row)
            item = AgateProcessedItem(
                run_id=rid,
                source_file="a.json",
                input_json="{}",
                status="succeeded",
                result_json=json.dumps({"ok": True}),
            )
            s.add(item)
            s.commit()
            s.refresh(item)
            iid = item.id

        bad = tc.patch(
            f"/runs/{rid}/items/{iid}",
            json={
                "overlay": {
                    "locations": {
                        "by_anchor": {
                            "x": {
                                "geocode": {
                                    "result": {
                                        "geometry": {"type": "Point", "coordinates": [999, 0]},
                                    }
                                }
                            }
                        }
                    }
                }
            },
            headers={"If-Match": '"0"'},
        )
        assert bad.status_code == 400
        detail = bad.json()["detail"]
        assert detail["error"] == "overlay_geometry_invalid"
    finally:
        app.dependency_overrides.clear()


def test_patch_processed_item_overlay_requires_if_match(tmp_path, monkeypatch):
    database_path = tmp_path / "agate-overlay-ifmatch.db"
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
        tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        project = tc.post("/projects", json={"name": "IfMatch", "slug": "ifmatch"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "Batch",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="b"),
            },
        ).json()
        with Session(engine) as s:
            row = _insert_pending_run(s, graph["id"])
            rid = row.id
            row.status = "succeeded"
            s.add(row)
            item = AgateProcessedItem(
                run_id=rid,
                source_file="x.json",
                input_json="{}",
                status="succeeded",
                result_json="{}",
            )
            s.add(item)
            s.commit()
            s.refresh(item)
            iid = item.id
        assert iid is not None

        bad = tc.patch(f"/runs/{rid}/items/{iid}", json={"overlay": {}})
        assert bad.status_code == 400
        assert "If-Match" in bad.json()["detail"]
    finally:
        app.dependency_overrides.clear()


def test_patch_processed_item_overlay_synthetic_404(monkeypatch, tmp_path):
    monkeypatch.setattr(runs.celery_app, "send_task", lambda *_a, **_k: None)
    database_path = tmp_path / "agate-synth-patch.db"
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
        tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        project = tc.post("/projects", json={"name": "Synth PATCH", "slug": "synth-patch"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "t",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="t"),
            },
        ).json()
        with Session(engine) as s:
            run_row = _insert_pending_run(s, graph["id"])
            rid = run_row.id
        r = tc.patch(
            f"/runs/{rid}/items/1",
            json={"overlay": {}},
            headers={"If-Match": '"0"'},
        )
        assert r.status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_get_run_processed_item_merged_locations_and_stale(tmp_path, monkeypatch):
    database_path = tmp_path / "agate-merged-lane.db"
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
        tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        project = tc.post("/projects", json={"name": "Merge lane", "slug": "merge-lane"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "Batch",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="b"),
            },
        ).json()
        with Session(engine) as s:
            row = _insert_pending_run(s, graph["id"])
            rid = row.id
        result = {
            "geocode_agent": {
                "text": "story",
                "places": {
                    "areas": {
                        "states": [],
                        "counties": [],
                        "cities": [
                            {
                                "id": "L1",
                                "description": "model",
                                "original_text": "ot",
                                "location": {"full": "A", "type": "city", "components": {}},
                            },
                        ],
                        "neighborhoods": [],
                        "regions": [],
                        "other": [],
                    },
                    "points": [],
                    "needs_review": [],
                },
            },
        }
        overlay = {
            "locations": {
                "by_anchor": {
                    "L1": {"description": "patched"},
                    "orphan": {"description": "gone"},
                },
                "user_added": [
                    {
                        "id": "user_place:11111111-1111-1111-1111-111111111111",
                        "location": {
                            "description": "user row",
                            "original_text": "u",
                            "location": {"full": "B", "type": "city", "components": {}},
                        },
                    }
                ],
            }
        }
        with Session(engine) as s:
            row = s.get(AgateRun, rid)
            assert row is not None
            row.status = "succeeded"
            s.add(row)
            item = AgateProcessedItem(
                run_id=rid,
                source_file="x.json",
                input_json="{}",
                status="succeeded",
                result_json=json.dumps(result),
                overlay_json=json.dumps(overlay),
                overlay_version=1,
            )
            s.add(item)
            s.commit()
            s.refresh(item)
            iid = item.id
        assert iid is not None

        resp = tc.get(f"/runs/{rid}/items/{iid}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["overlay_version"] == 1
        assert len(body["merged_locations"]) == 2
        by_anchor = {r["anchor"]: r for r in body["merged_locations"]}
        assert by_anchor["L1"]["source"] == "model"
        assert by_anchor["L1"]["location"]["description"] == "patched"
        uid = "user_place:11111111-1111-1111-1111-111111111111"
        assert by_anchor[uid]["source"] == "user"
        assert by_anchor[uid]["location"]["description"] == "user row"
        assert len(body["stale_overlay_entries"]) == 1
        assert body["stale_overlay_entries"][0]["anchor"] == "orphan"
        assert body["stale_overlay_entries"][0]["reason"] == "anchor_missing_from_model_output"
        ac = body["article_context"]
        assert ac["resolution"] in ("none", "inline_fallback")
        assert "body" in ac
    finally:
        app.dependency_overrides.clear()


def test_get_run_processed_item_failed_does_not_bleed_batch_substrate(tmp_path, monkeypatch):
    """Failed items without article_id must not show sibling batch entities in review lanes."""
    database_path = tmp_path / "agate-failed-batch-bleed.db"
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
        tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        project = tc.post("/projects", json={"name": "Batch bleed", "slug": "batch-bleed"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "Batch",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="b"),
            },
        ).json()
        with Session(engine) as s:
            row = _insert_pending_run(s, graph["id"])
            rid = row.id
        pid = int(project["id"])

        with Session(engine) as s:
            row = s.get(AgateRun, rid)
            assert row is not None
            row.status = "running"
            s.add(row)

            sibling_article = SubstrateArticle(
                project_id=pid,
                headline="Sibling story",
                text="Other article body",
            )
            s.add(sibling_article)
            s.commit()
            s.refresh(sibling_article)

            person = SubstratePerson(
                project_id=pid,
                name="Sibling Person",
                normalized_name="sibling person",
                source_details_json={"run_id": rid, "raw_entry_id": "p1"},
            )
            s.add(person)
            s.commit()
            s.refresh(person)
            s.add(
                SubstratePersonMention(
                    article_id=int(sibling_article.id),
                    person_id=int(person.id),
                )
            )

            ok_item = AgateProcessedItem(
                run_id=rid,
                source_file="ok.json",
                input_json=json.dumps({"headline": "Sibling story", "text": "Other article body"}),
                status="succeeded",
                result_json=json.dumps(
                    {
                        "stylebook_output": {
                            "article_id": int(sibling_article.id),
                            "people": [{"id": "p1", "name": "Sibling Person"}],
                        }
                    }
                ),
            )
            s.add(ok_item)

            failed_item = AgateProcessedItem(
                run_id=rid,
                source_file="failed.json",
                input_json=json.dumps(
                    {
                        "headline": "Horoscope",
                        "text": "Moon in Capricorn today.",
                    }
                ),
                status="failed",
                error_message="PlaceExtract timed out",
                result_json=None,
            )
            s.add(failed_item)
            s.commit()
            s.refresh(failed_item)
            failed_id = failed_item.id
        assert failed_id is not None

        resp = tc.get(f"/runs/{rid}/items/{failed_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert body["output"] is None
        assert body["merged_people"] == []
        assert body["merged_locations"] == []
        assert body["merged_organizations"] == []
        assert body["article_context"]["headline"] == "Horoscope"
    finally:
        app.dependency_overrides.clear()


def test_get_run_processed_item_article_context_substrate(tmp_path, monkeypatch):
    database_path = tmp_path / "agate-article-ctx.db"
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
        tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        project = tc.post("/projects", json={"name": "Art Ctx", "slug": "art-ctx-sub"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "G",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="b"),
            },
        ).json()
        with Session(engine) as s:
            row = _insert_pending_run(s, graph["id"])
            rid = row.id
        pid = int(project["id"])
        with Session(engine) as s:
            art = SubstrateArticle(
                project_id=pid,
                headline="Story HL",
                text="Full article from substrate.",
                url=f"https://example.com/substrate-article-{pid}",
            )
            s.add(art)
            s.commit()
            s.refresh(art)
            aid = int(art.id)
            row = s.get(AgateRun, rid)
            assert row is not None
            row.status = "succeeded"
            s.add(row)
            item = AgateProcessedItem(
                run_id=rid,
                source_file="doc.json",
                input_json=json.dumps(
                    {
                        "input_article_id": aid,
                        "text": (
                            "shorter inline should not replace substrate body"
                        ),
                    }
                ),
                status="succeeded",
                result_json=json.dumps({"n": {"locations": []}}),
                overlay_version=0,
            )
            s.add(item)
            s.commit()
            s.refresh(item)
            iid = item.id
        assert iid is not None

        resp = tc.get(f"/runs/{rid}/items/{iid}")
        assert resp.status_code == 200
        ac = resp.json()["article_context"]
        assert ac["resolution"] == "substrate"
        assert ac["article_id"] == aid
        assert ac["body"] == "Full article from substrate."
        assert ac["headline"] == "Story HL"
        assert ac["reason"] is None
    finally:
        app.dependency_overrides.clear()


def test_get_run_processed_item_article_context_inline_only(tmp_path, monkeypatch):
    database_path = tmp_path / "agate-article-inline.db"
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
        tc = TestClient(app, headers={"Authorization": "Bearer backfield-dev"})
        project = tc.post("/projects", json={"name": "Art Inline", "slug": "art-inline"}).json()
        graph = tc.post(
            "/graphs",
            json={
                "name": "G2",
                "project_id": project["id"],
                "spec": _minimal_text_input_spec(name="b"),
            },
        ).json()
        with Session(engine) as s:
            row = _insert_pending_run(s, graph["id"])
            rid = row.id
            row.status = "succeeded"
            s.add(row)
            item = AgateProcessedItem(
                run_id=rid,
                source_file="doc.json",
                input_json=json.dumps(
                    {"headline": "Inline title", "article_text": "longer body text", "text": "x"}
                ),
                status="succeeded",
                result_json="{}",
                overlay_version=0,
            )
            s.add(item)
            s.commit()
            s.refresh(item)
            iid = item.id
        resp = tc.get(f"/runs/{rid}/items/{iid}")
        assert resp.status_code == 200
        ac = resp.json()["article_context"]
        assert ac["resolution"] == "inline_fallback"
        assert ac["reason"] == "no_input_article_id"
        assert ac["body"] == "longer body text"
        assert ac["headline"] == "Inline title"
    finally:
        app.dependency_overrides.clear()


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
        assert body.get("workspace_stylebook_id") == sb_id
        assert body.get("workspace_stylebook_name") == "Default Stylebook"
        assert body.get("workspace_stylebook_slug") == "default"
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
