"""Integration-style tests for Agate API without Docker."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from api.deps import get_session
from api.main import app
from api.routers import runs
from backfield_auth import create_session_token
from backfield_db import (
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldProject,
    BackfieldUser,
    BackfieldWorkspace,
    BackfieldWorkspaceMembership,
)
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
    assert sent_task == {
        "name": "worker.tasks.execute_agate_run",
        "args": [run["id"]],
        "queue": "agate",
    }

    list_response = client.get("/graphs")
    assert list_response.status_code == 200
    assert len(list_response.json()) == 1


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
        ws = BackfieldWorkspace(
            organization_id=int(org.id), name="Default Workspace", slug="default"
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
        pid = int(r.json()["id"])
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
        ws_a = BackfieldWorkspace(
            organization_id=oid, name="Workspace A", slug="ws-a"
        )
        ws_b = BackfieldWorkspace(
            organization_id=oid, name="Workspace B", slug="ws-b"
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
        ws_b = BackfieldWorkspace(
            organization_id=oid, name="Workspace B", slug="ws-b2"
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
