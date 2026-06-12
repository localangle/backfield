"""Tests for Core API `/public/v1` routes."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from core_api.deps import get_session
from core_api.main import app
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture
def public_client(tmp_path) -> Generator[TestClient, None, None]:
    database_path = tmp_path / "public-api-test.db"
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
        s.add(
            BackfieldProject(
                name="Other",
                slug="other",
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
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _create_project_api_key(client: TestClient, project_id: int = 1) -> str:
    client.post(
        "/v1/bootstrap/first-user",
        json={"email": "pub@example.com", "password": "pub-secret-12"},
    )
    client.post(
        "/v1/auth/login",
        json={"email": "pub@example.com", "password": "pub-secret-12"},
    )
    created = client.post(
        f"/v1/projects/{project_id}/api-keys",
        json={"credential_type": "user", "label": "public-api"},
    )
    assert created.status_code == 200
    return str(created.json()["raw_key"])


def test_public_project_requires_api_key(public_client: TestClient) -> None:
    r = public_client.get("/public/v1/projects/general")
    assert r.status_code == 401


def test_public_project_rejects_session_cookie(public_client: TestClient) -> None:
    public_client.post(
        "/v1/bootstrap/first-user",
        json={"email": "sesspub@example.com", "password": "sesspub-secret-12"},
    )
    public_client.post(
        "/v1/auth/login",
        json={"email": "sesspub@example.com", "password": "sesspub-secret-12"},
    )
    r = public_client.get("/public/v1/projects/general")
    assert r.status_code == 401


def test_public_project_metadata(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    r = public_client.get(
        "/public/v1/projects/general",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "general"
    assert body["name"] == "General"
    assert body["id"] == 1
    assert body["stylebook_slug"] == "default"
    assert body["stylebook_name"]


def test_public_project_unknown_slug(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client)
    r = public_client.get(
        "/public/v1/projects/no-such-project",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert r.status_code == 404


def test_public_project_wrong_project_key(public_client: TestClient) -> None:
    raw_key = _create_project_api_key(public_client, project_id=1)
    r = public_client.get(
        "/public/v1/projects/other",
        headers={"Authorization": f"Bearer {raw_key}"},
    )
    assert r.status_code == 403


def test_public_project_service_token(public_client: TestClient) -> None:
    r = public_client.get(
        "/public/v1/projects/general",
        headers={"Authorization": "Bearer backfield-dev"},
    )
    assert r.status_code == 200
    assert r.json()["slug"] == "general"
