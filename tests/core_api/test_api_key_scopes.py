"""Tests for project API key scopes."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from backfield_auth.gate import (
    SCOPE_READ,
    SCOPE_RUNS_TRIGGER,
    parse_scopes,
)
from backfield_db import BackfieldOrganization, BackfieldProject, BackfieldWorkspace
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from core_api.deps import get_session
from core_api.main import app
from core_api.routers.public.deps import require_scope
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from tests.core_api.auth_helpers import attach_test_engine, seed_first_admin


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "api-key-scopes-test.db"
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


def test_parse_scopes_defaults() -> None:
    assert parse_scopes(None) == [SCOPE_READ]
    assert parse_scopes("") == [SCOPE_READ]
    assert parse_scopes("read") == [SCOPE_READ]


def test_parse_scopes_runs_trigger() -> None:
    assert parse_scopes("read runs:trigger") == [SCOPE_READ, SCOPE_RUNS_TRIGGER]


def test_parse_scopes_filters_unknown() -> None:
    assert parse_scopes("read foo") == [SCOPE_READ]


def test_create_api_key_defaults_to_read_scope(client: TestClient) -> None:
    seed_first_admin(client, "default@example.com", "default-secret")
    client.post(
        "/v1/auth/login",
        json={"email": "default@example.com", "password": "default-secret"},
    )
    created = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": "user", "label": "read-only"},
    )
    assert created.status_code == 200
    assert created.json()["scopes"] == [SCOPE_READ]

    listed = client.get("/v1/projects/1/api-keys").json()
    assert listed[0]["scopes"] == [SCOPE_READ]


def test_create_service_key_with_runs_trigger(client: TestClient) -> None:
    seed_first_admin(client, "svc@example.com", "svc-secret")
    client.post(
        "/v1/auth/login",
        json={"email": "svc@example.com", "password": "svc-secret"},
    )
    created = client.post(
        "/v1/projects/1/api-keys",
        json={
            "credential_type": "service",
            "label": "ci-trigger",
            "scopes": ["runs:trigger"],
        },
    )
    assert created.status_code == 200
    assert created.json()["scopes"] == [SCOPE_READ, SCOPE_RUNS_TRIGGER]


def test_create_user_key_with_runs_trigger_rejected(client: TestClient) -> None:
    seed_first_admin(client, "usertr@example.com", "usertr-secret")
    client.post(
        "/v1/auth/login",
        json={"email": "usertr@example.com", "password": "usertr-secret"},
    )
    r = client.post(
        "/v1/projects/1/api-keys",
        json={
            "credential_type": "user",
            "label": "bad",
            "scopes": ["runs:trigger"],
        },
    )
    assert r.status_code == 400
    assert "service key" in r.json()["detail"].lower()


def test_create_api_key_unknown_scope_rejected(client: TestClient) -> None:
    seed_first_admin(client, "unk@example.com", "unk-secret")
    client.post(
        "/v1/auth/login",
        json={"email": "unk@example.com", "password": "unk-secret"},
    )
    r = client.post(
        "/v1/projects/1/api-keys",
        json={
            "credential_type": "service",
            "label": "bad-scope",
            "scopes": ["admin:all"],
        },
    )
    assert r.status_code == 400
    assert "unknown scope" in r.json()["detail"].lower()


def test_require_scope_enforcement() -> None:
    dep = require_scope(SCOPE_RUNS_TRIGGER)

    with pytest.raises(HTTPException) as exc:
        dep(auth={"type": "api_key", "scopes": [SCOPE_READ]})
    assert exc.value.status_code == 403
    assert SCOPE_RUNS_TRIGGER in exc.value.detail

    auth = {"type": "api_key", "scopes": [SCOPE_READ, SCOPE_RUNS_TRIGGER]}
    assert dep(auth=auth) == auth

    service_auth = {"type": "service", "is_admin": True}
    assert dep(auth=service_auth) == service_auth
