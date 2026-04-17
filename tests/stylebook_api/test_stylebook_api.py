"""Integration-style tests for Stylebook API (no Docker)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from backfield_db import BackfieldOrganization, Stylebook
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from stylebook_api.deps import get_session
from stylebook_api.main import app


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("SERVICE_API_TOKEN", "backfield-dev")
    import importlib

    import backfield_auth.service_tokens as service_tokens

    importlib.reload(service_tokens)

    database_path = tmp_path / "stylebook-api-test.db"
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
        s.add(
            Stylebook(
                organization_id=oid,
                slug="default",
                name="Default Stylebook",
                is_default=True,
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


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json().get("ok") is True


def test_geocode_resolve_requires_auth(client: TestClient) -> None:
    r = client.post("/v1/geocode/resolve", json={"query": "Chicago, IL"})
    assert r.status_code == 401


def test_geocode_resolve_with_service_bearer(client: TestClient) -> None:
    r = client.post(
        "/v1/geocode/resolve",
        json={"query": "Chicago, IL"},
        headers={"Authorization": "Bearer backfield-dev"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("lat") is not None


def test_list_stylebooks_service(client: TestClient) -> None:
    r = client.get(
        "/v1/organizations/1/stylebooks",
        headers={"Authorization": "Bearer backfield-dev"},
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["slug"] == "default"
