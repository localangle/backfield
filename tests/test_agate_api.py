"""Integration-style tests for Agate API without Docker."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from api.deps import get_session
from api.main import app
from api.routers import runs
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

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}


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
    assert sent_task == {
        "name": "worker.tasks.execute_agate_run",
        "args": [run["id"]],
        "queue": "agate",
    }

    list_response = client.get("/graphs")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


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
