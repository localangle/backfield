"""Integration-style tests for Agate API without Docker."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from api.deps import get_session
from api.main import app
from api.routers import runs
from backfield_db import BackfieldOrganization
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
        s.add(BackfieldOrganization(name="Default", slug="default"))
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


def test_projects_require_auth(tmp_path):
    """Unauthenticated requests to protected routes return 401."""
    database_path = tmp_path / "agate-noauth.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        s.add(BackfieldOrganization(name="Default", slug="default"))
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
    assert sent_task == {
        "name": "worker.tasks.execute_agate_run",
        "args": [run["id"]],
        "queue": "agate",
    }

    list_response = client.get("/graphs")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1
