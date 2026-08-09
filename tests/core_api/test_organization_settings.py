"""Core API organization settings (map default viewport)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from backfield_db import BackfieldOrganization
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from core_api.deps import get_session
from core_api.main import app
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from tests.core_api.auth_helpers import attach_test_engine, seed_and_login
from tests.integration_helpers import patch_test_engine


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("SERVICE_API_TOKEN", "backfield-dev")
    import importlib

    import backfield_auth.service_tokens as service_tokens

    importlib.reload(service_tokens)

    database_path = tmp_path / "core-org-settings.db"
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    patch_test_engine(monkeypatch, engine)

    with Session(engine) as s:
        org = BackfieldOrganization(name="Backfield", slug="default")
        s.add(org)
        s.commit()
        s.refresh(org)
        ensure_default_stylebook_for_organization(s, int(org.id))
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        yield attach_test_engine(TestClient(app), engine)
    finally:
        app.dependency_overrides.clear()


def test_org_settings_map_viewport_round_trip(client: TestClient) -> None:
    seed_and_login(client, "admin@example.com", "admin-secret-12")

    empty = client.get("/v1/organizations/1/settings")
    assert empty.status_code == 200
    assert empty.json()["map_default_viewport"] is None

    saved = client.patch(
        "/v1/organizations/1/settings",
        json={"map_default_viewport": {"lat": 41.88, "lng": -87.63, "zoom": 11}},
    )
    assert saved.status_code == 200
    body = saved.json()["map_default_viewport"]
    assert body["lat"] == pytest.approx(41.88)
    assert body["lng"] == pytest.approx(-87.63)
    assert body["zoom"] == pytest.approx(11)

    again = client.get("/v1/organizations/1/settings")
    assert again.status_code == 200
    assert again.json()["map_default_viewport"]["zoom"] == pytest.approx(11)

    cleared = client.patch(
        "/v1/organizations/1/settings",
        json={"map_default_viewport": None},
    )
    assert cleared.status_code == 200
    assert cleared.json()["map_default_viewport"] is None


def test_org_settings_patch_requires_admin(client: TestClient) -> None:
    seed_and_login(client, "admin@example.com", "admin-secret-12")
    create = client.post(
        "/v1/organizations/1/users",
        json={
            "email": "member@example.com",
            "password": "member-secret-12",
            "role": "member",
        },
    )
    assert create.status_code in {200, 201}
    client.post("/v1/auth/logout")
    login = client.post(
        "/v1/auth/login",
        json={"email": "member@example.com", "password": "member-secret-12"},
    )
    assert login.status_code == 200

    read = client.get("/v1/organizations/1/settings")
    assert read.status_code == 200

    write = client.patch(
        "/v1/organizations/1/settings",
        json={"map_default_viewport": {"lat": 40.0, "lng": -74.0, "zoom": 10}},
    )
    assert write.status_code == 403
