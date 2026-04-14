"""Integration tests for Core API (SQLite, no Docker)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from backfield_db import BackfieldOrganization, BackfieldProject
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
        s.add(
            BackfieldProject(
                name="General",
                slug="general",
                organization_id=int(org.id),
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
