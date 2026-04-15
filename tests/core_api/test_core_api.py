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
        org = BackfieldOrganization(name="Backfield", slug="default")
        s.add(org)
        s.commit()
        s.refresh(org)
        ws = BackfieldWorkspace(
            organization_id=int(org.id),
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
                organization_id=int(org.id),
                workspace_id=int(ws.id),
            )
        )
        s.add(
            BackfieldProject(
                name="Other",
                slug="other",
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
    assert body.get("organization_name") == "Backfield"

    who = client.get("/v1/secure/whoami")
    assert who.status_code == 200
    w = who.json()
    assert w.get("auth_type") == "session"
    assert w.get("email") == "owner@example.com"


def test_secure_whoami_service_token(client: TestClient) -> None:
    r = client.get("/v1/secure/whoami", headers={"Authorization": "Bearer backfield-dev"})
    assert r.status_code == 200
    assert r.json().get("auth_type") == "service"


def test_me_workspaces_requires_auth(client: TestClient) -> None:
    r = client.get("/v1/me/workspaces")
    assert r.status_code == 401


def test_me_workspaces_groups_projects_for_org_admin(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "ws@example.com", "password": "ws-secret-12"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "ws@example.com", "password": "ws-secret-12"},
    )
    r = client.get("/v1/me/workspaces")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    default_ws = next(w for w in data if w["slug"] == "default")
    slugs = {p["slug"] for p in default_ws["projects"]}
    assert "general" in slugs
    assert "other" in slugs


def test_create_workspace_requires_auth(client: TestClient) -> None:
    r = client.post("/v1/organizations/1/workspaces", json={"name": "Nope"})
    assert r.status_code == 401


def test_patch_workspace_requires_auth(client: TestClient) -> None:
    r = client.patch("/v1/organizations/1/workspaces/1", json={"name": "Nope"})
    assert r.status_code == 401


def test_patch_workspace_name_org_admin(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "wspatch@example.com", "password": "wspatch-secret-9"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "wspatch@example.com", "password": "wspatch-secret-9"},
    )
    org_id = client.get("/v1/auth/me").json()["organization_id"]
    listed = client.get("/v1/me/workspaces").json()
    wid = next(w for w in listed if w["slug"] == "default")["id"]
    r = client.patch(
        f"/v1/organizations/{org_id}/workspaces/{wid}",
        json={"name": "Editorial desk"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Editorial desk"
    assert body["slug"] == "default"
    assert "general" in {p["slug"] for p in body["projects"]}


def test_create_workspace_org_admin_and_me_lists_empty(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "cws@example.com", "password": "cws-secret-12"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "cws@example.com", "password": "cws-secret-12"},
    )
    org_id = client.get("/v1/auth/me").json()["organization_id"]
    assert org_id is not None
    r = client.post(f"/v1/organizations/{org_id}/workspaces", json={"name": "Investigations"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Investigations"
    assert body["projects"] == []
    assert body["slug"] == "investigations"

    listed = client.get("/v1/me/workspaces").json()
    inv = next(w for w in listed if w["slug"] == "investigations")
    assert inv["projects"] == []


def test_patch_organization_requires_auth(client: TestClient) -> None:
    r = client.patch("/v1/organizations/1", json={"name": "Nope"})
    assert r.status_code == 401


def test_patch_organization_name_org_admin(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "orgpatch@example.com", "password": "orgpatch-secret-9"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "orgpatch@example.com", "password": "orgpatch-secret-9"},
    )
    org_id = client.get("/v1/auth/me").json()["organization_id"]
    assert org_id is not None
    r = client.patch(f"/v1/organizations/{org_id}", json={"name": "River Gazette"})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "River Gazette"
    assert body["slug"] == "default"
    me = client.get("/v1/auth/me").json()
    assert me.get("organization_name") == "River Gazette"


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
    assert len(projects) >= 2
    slugs = {p["slug"] for p in projects}
    assert "general" in slugs
    assert "other" in slugs

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
    assert keys.json() == []

    mk = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": "user", "label": "member-key"},
    )
    assert mk.status_code == 200
    assert mk.json().get("user_id") == member_id
    listed = client.get("/v1/projects/1/api-keys").json()
    assert len(listed) == 1
    assert listed[0]["user_id"] == member_id


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
    created = create.json()
    raw_key = created["raw_key"]
    assert created.get("user_id") == 1

    listed = client.get(
        "/v1/projects/1/api-keys",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["key_prefix"] == raw_key[:22]
    assert rows[0].get("user_id") == 1

    who = client.get(
        "/v1/secure/whoami",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert who.status_code == 200
    assert who.json().get("auth_type") == "api_key"


def test_api_keys_no_auth_returns_401(client: TestClient) -> None:
    r = client.get("/v1/projects/1/api-keys")
    assert r.status_code == 401


def test_api_keys_invalid_bearer_returns_401(client: TestClient) -> None:
    r = client.get(
        "/v1/projects/1/api-keys",
        headers={"Authorization": "Bearer bfk_notvalidtokenatall"},
    )
    assert r.status_code == 401


def test_api_keys_wrong_project_bearer_returns_403(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "wp@example.com", "password": "wp-secret"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "wp@example.com", "password": "wp-secret"},
    )
    create = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": "user", "label": "p1"},
    )
    assert create.status_code == 200
    raw_key = create.json()["raw_key"]

    r = client.get(
        "/v1/projects/2/api-keys",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert r.status_code == 403
    assert "project" in r.json().get("detail", "").lower()


def test_api_keys_revoked_bearer_returns_401(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "rv@example.com", "password": "rv-secret"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "rv@example.com", "password": "rv-secret"},
    )
    created = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": "user", "label": "revoke-me"},
    ).json()
    raw_key = created["raw_key"]
    cid = created["id"]

    assert (
        client.get(
            "/v1/projects/1/api-keys",
            headers={"Authorization": f"Bearer {raw_key}"},
        ).status_code
        == 200
    )

    client.delete(f"/v1/projects/1/api-keys/{cid}")
    client.post("/v1/auth/logout")

    r = client.get(
        "/v1/projects/1/api-keys",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert r.status_code == 401


def test_api_keys_post_user_key_requires_session_not_bearer(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "sess@example.com", "password": "sess-secret"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "sess@example.com", "password": "sess-secret"},
    )
    raw = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": "user", "label": "a"},
    ).json()["raw_key"]
    client.post("/v1/auth/logout")

    r = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": "user", "label": "b"},
        headers={"Authorization": f"Bearer {raw}"},
    )
    assert r.status_code == 400
    assert "session" in r.json()["detail"].lower()


def test_api_keys_post_service_key_forbidden_for_member(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "oadmin@example.com", "password": "oa-secret"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "oadmin@example.com", "password": "oa-secret"},
    )
    org_id = client.get("/v1/auth/me").json()["organization_id"]
    client.post(
        f"/v1/organizations/{org_id}/users",
        json={
            "email": "plain@example.com",
            "password": "plain-secret",
            "role": "member",
        },
    )
    ws_id = client.get(f"/v1/organizations/{org_id}/workspaces").json()[0]["id"]
    mid = client.get(f"/v1/organizations/{org_id}/users?detail=true").json()
    member_id = next(u["id"] for u in mid if u["email"] == "plain@example.com")
    client.put(
        f"/v1/organizations/{org_id}/users/{member_id}/workspace-memberships",
        json={"workspace_ids": [ws_id]},
    )
    client.post("/v1/auth/logout")
    client.post(
        "/v1/auth/login",
        json={"email": "plain@example.com", "password": "plain-secret"},
    )

    r = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": "service", "label": "ci"},
    )
    assert r.status_code == 403


def test_api_keys_member_cannot_revoke_another_users_key(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "adm2@example.com", "password": "adm2-secret"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "adm2@example.com", "password": "adm2-secret"},
    )
    org_id = client.get("/v1/auth/me").json()["organization_id"]
    ws_id = client.get(f"/v1/organizations/{org_id}/workspaces").json()[0]["id"]
    for email, pw in (
        ("alice@example.com", "alice-secret"),
        ("bob@example.com", "bob-secret"),
    ):
        client.post(
            f"/v1/organizations/{org_id}/users",
            json={"email": email, "password": pw, "role": "member"},
        )
    users = client.get(f"/v1/organizations/{org_id}/users?detail=true").json()
    alice_id = next(u["id"] for u in users if u["email"] == "alice@example.com")
    bob_id = next(u["id"] for u in users if u["email"] == "bob@example.com")
    client.put(
        f"/v1/organizations/{org_id}/users/{alice_id}/workspace-memberships",
        json={"workspace_ids": [ws_id]},
    )
    client.put(
        f"/v1/organizations/{org_id}/users/{bob_id}/workspace-memberships",
        json={"workspace_ids": [ws_id]},
    )

    client.post("/v1/auth/logout")
    client.post(
        "/v1/auth/login",
        json={"email": "alice@example.com", "password": "alice-secret"},
    )
    cred_id = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": "user", "label": "alice-key"},
    ).json()["id"]

    client.post("/v1/auth/logout")
    client.post(
        "/v1/auth/login",
        json={"email": "bob@example.com", "password": "bob-secret"},
    )

    r = client.delete(f"/v1/projects/1/api-keys/{cred_id}")
    assert r.status_code == 403


def test_api_keys_revoke_with_bearer_forbidden_even_for_own_row(client: TestClient) -> None:
    """Project API key must not be able to revoke credentials (no session identity)."""
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "br@example.com", "password": "br-secret"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "br@example.com", "password": "br-secret"},
    )
    created = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": "user", "label": "self"},
    ).json()
    raw_key = created["raw_key"]
    cid = created["id"]
    client.post("/v1/auth/logout")

    r = client.delete(
        f"/v1/projects/1/api-keys/{cid}",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert r.status_code == 403
    assert "session" in r.json()["detail"].lower()


def test_api_keys_org_admin_creates_revokes_service_key(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "svc@example.com", "password": "svc-secret"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "svc@example.com", "password": "svc-secret"},
    )
    created = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": "service", "label": "deploy"},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["credential_type"] == "service"
    assert body.get("user_id") is None
    raw_key = body["raw_key"]

    listed = client.get("/v1/projects/1/api-keys").json()
    assert len(listed) == 1
    assert listed[0]["credential_type"] == "service"

    assert (
        client.get(
            "/v1/projects/1/api-keys",
            headers={"Authorization": f"Bearer {raw_key}"},
        ).status_code
        == 200
    )

    cid = body["id"]
    dr = client.delete(f"/v1/projects/1/api-keys/{cid}")
    assert dr.status_code == 204
    client.post("/v1/auth/logout")

    assert (
        client.get(
            "/v1/projects/1/api-keys",
            headers={"Authorization": f"Bearer {raw_key}"},
        ).status_code
        == 401
    )


def test_api_keys_org_admin_revokes_other_users_user_key(client: TestClient) -> None:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "adm3@example.com", "password": "adm3-secret"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "adm3@example.com", "password": "adm3-secret"},
    )
    org_id = client.get("/v1/auth/me").json()["organization_id"]
    ws_id = client.get(f"/v1/organizations/{org_id}/workspaces").json()[0]["id"]
    client.post(
        f"/v1/organizations/{org_id}/users",
        json={"email": "target@example.com", "password": "t-secret", "role": "member"},
    )
    uid = client.get(f"/v1/organizations/{org_id}/users?detail=true").json()
    target_id = next(u["id"] for u in uid if u["email"] == "target@example.com")
    client.put(
        f"/v1/organizations/{org_id}/users/{target_id}/workspace-memberships",
        json={"workspace_ids": [ws_id]},
    )

    client.post("/v1/auth/logout")
    client.post(
        "/v1/auth/login",
        json={"email": "target@example.com", "password": "t-secret"},
    )
    cred_id = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": "user", "label": "member"},
    ).json()["id"]

    client.post("/v1/auth/logout")
    client.post(
        "/v1/auth/login",
        json={"email": "adm3@example.com", "password": "adm3-secret"},
    )

    assert client.delete(f"/v1/projects/1/api-keys/{cred_id}").status_code == 204
    assert client.get("/v1/projects/1/api-keys").json() == []
