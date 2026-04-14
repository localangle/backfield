"""Integration tests for Core API (SQLite, no Docker)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from backfield_db import BackfieldOrganization, BackfieldProject, BackfieldWorkspace
from core_api.deps import get_session
from core_api.main import app
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "core-api-test.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as s:
        org = BackfieldOrganization(name="Default", slug="default")
        s.add(org)
        s.commit()
        s.refresh(org)
        ws = BackfieldWorkspace(
            organization_id=int(org.id),
            name="Default",
            slug="default",
        )
        s.add(ws)
        s.commit()
        s.refresh(ws)
        s.add(
            BackfieldProject(
                name="General",
                slug="general",
                organization_id=int(org.id),
                workspace_id=int(ws.id),
            )
        )
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_public_ping(client: TestClient) -> None:
    r = client.get("/v1/public/ping")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "scope": "public"}


def test_bootstrap_login_me_whoami(client: TestClient) -> None:
    boot = client.post(
        "/v1/bootstrap/first-user",
        json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
    )
    assert boot.status_code == 200
    assert boot.json().get("ok") is True

    login = client.post(
        "/v1/auth/login",
        json={"email": "owner@example.com", "password": "correct-horse-battery-staple"},
    )
    assert login.status_code == 200

    me = client.get("/v1/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body.get("authenticated") is True
    assert body.get("email") == "owner@example.com"
    assert body.get("organization_id") is not None

    who = client.get("/v1/secure/whoami")
    assert who.status_code == 200
    w = who.json()
    assert w.get("auth_type") == "session"
    assert w.get("email") == "owner@example.com"


def test_secure_whoami_service_token(client: TestClient) -> None:
    r = client.get("/v1/secure/whoami", headers={"Authorization": "Bearer backfield-dev"})
    assert r.status_code == 200
    assert r.json().get("auth_type") == "service"


def test_change_password(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "pw@example.com", "password": "original-secret"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "pw@example.com", "password": "original-secret"},
    )
    bad = client.post(
        "/v1/auth/change-password",
        json={"current_password": "wrong", "new_password": "new-secret"},
    )
    assert bad.status_code == 401
    ok = client.post(
        "/v1/auth/change-password",
        json={"current_password": "original-secret", "new_password": "new-secret"},
    )
    assert ok.status_code == 200
    client.post("/v1/auth/logout")
    fail_login = client.post(
        "/v1/auth/login",
        json={"email": "pw@example.com", "password": "original-secret"},
    )
    assert fail_login.status_code == 401
    good_login = client.post(
        "/v1/auth/login",
        json={"email": "pw@example.com", "password": "new-secret"},
    )
    assert good_login.status_code == 200


def test_org_admin_list_projects_and_users_detail(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "admin@example.com", "password": "admin-secret"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "admin-secret"},
    )
    me = client.get("/v1/auth/me").json()
    org_id = me["organization_id"]
    assert org_id is not None

    pr = client.get(f"/v1/organizations/{org_id}/projects")
    assert pr.status_code == 200
    projects = pr.json()
    assert len(projects) >= 1
    assert projects[0]["slug"] == "general"

    users = client.get(f"/v1/organizations/{org_id}/users?detail=true")
    assert users.status_code == 200
    rows = users.json()
    assert len(rows) == 1
    assert rows[0]["email"] == "admin@example.com"
    assert rows[0]["role"] == "org_admin"
    assert rows[0]["project_memberships"] is not None
    assert rows[0]["workspace_memberships"] is not None

    wlist = client.get(f"/v1/organizations/{org_id}/workspaces")
    assert wlist.status_code == 200
    wdata = wlist.json()
    assert len(wdata) >= 1
    assert wdata[0]["slug"] == "default"
    assert len(wdata[0]["projects"]) >= 1


def test_member_workspace_memberships_grant_project_access(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "wsadmin@example.com", "password": "ws-admin-secret"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "wsadmin@example.com", "password": "ws-admin-secret"},
    )
    me = client.get("/v1/auth/me").json()
    org_id = me["organization_id"]

    create = client.post(
        f"/v1/organizations/{org_id}/users",
        json={
            "email": "member@example.com",
            "password": "member-secret",
            "role": "member",
        },
    )
    assert create.status_code == 200
    member_id = create.json()["id"]

    ws_list = client.get(f"/v1/organizations/{org_id}/workspaces").json()
    ws_id = ws_list[0]["id"]

    put = client.put(
        f"/v1/organizations/{org_id}/users/{member_id}/workspace-memberships",
        json={"workspace_ids": [ws_id]},
    )
    assert put.status_code == 200
    assert len(put.json()) == 1

    users = client.get(f"/v1/organizations/{org_id}/users?detail=true").json()
    member_row = next(r for r in users if r["email"] == "member@example.com")
    assert len(member_row["workspace_memberships"]) == 1
    assert member_row["workspace_memberships"][0]["id"] == ws_id

    client.post("/v1/auth/logout")
    client.post(
        "/v1/auth/login",
        json={"email": "member@example.com", "password": "member-secret"},
    )
    keys = client.get("/v1/projects/1/api-keys")
    assert keys.status_code == 200


def test_project_api_key_bearer(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "keyuser@example.com", "password": "shortpw"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "keyuser@example.com", "password": "shortpw"},
    )
    create = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": "user", "label": "ci"},
    )
    assert create.status_code == 200
    raw_key = create.json()["raw_key"]

    listed = client.get(
        "/v1/projects/1/api-keys",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["key_prefix"] == raw_key[:22]

    who = client.get(
        "/v1/secure/whoami",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert who.status_code == 200
    assert who.json().get("auth_type") == "api_key"
