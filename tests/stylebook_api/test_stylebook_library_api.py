"""Tests for org stylebook library routes (Issue 3)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    Stylebook,
)
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine
from stylebook_api.deps import get_session
from stylebook_api.main import app


@pytest.fixture
def _library_client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("SERVICE_API_TOKEN", "backfield-dev")
    import importlib

    import backfield_auth.service_tokens as service_tokens

    importlib.reload(service_tokens)

    database_path = tmp_path / "stylebook-lib-api.db"
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
        sb = Stylebook(
            organization_id=oid,
            slug="default",
            name="Default Stylebook",
            is_default=True,
        )
        s.add(sb)
        s.commit()
        s.refresh(sb)
        sb_id = int(sb.id)
        ws = BackfieldWorkspace(
            organization_id=oid,
            stylebook_id=sb_id,
            name="Default workspace",
            slug="default-ws",
        )
        s.add(ws)
        s.commit()
        s.refresh(ws)
        wid = int(ws.id)
        s.add(
            BackfieldProject(
                organization_id=oid,
                name="Demo",
                slug="demo-proj",
                workspace_id=wid,
            )
        )
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client(_library_client: TestClient) -> TestClient:
    return _library_client


def _service_headers() -> dict[str, str]:
    return {"Authorization": "Bearer backfield-dev"}


def test_get_stylebook_by_slug_default(client: TestClient) -> None:
    r = client.get(
        "/v1/organizations/1/stylebooks/by-slug/default",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "default"
    assert body["name"] == "Default Stylebook"


def test_create_list_patch_delete_flow(client: TestClient) -> None:
    r = client.post(
        "/v1/organizations/1/stylebooks",
        headers=_service_headers(),
        json={"name": "Regional", "is_default": False},
    )
    assert r.status_code == 200
    regional = r.json()
    assert regional["name"] == "Regional"
    assert regional["slug"] != ""
    rid = regional["id"]

    r2 = client.post(
        "/v1/organizations/1/stylebooks",
        headers=_service_headers(),
        json={"name": "Regional"},
    )
    assert r2.status_code == 400

    r3 = client.patch(
        f"/v1/organizations/1/stylebooks/{rid}",
        headers=_service_headers(),
        json={"name": "Regional Updated"},
    )
    assert r3.status_code == 200
    assert r3.json()["name"] == "Regional Updated"

    pv = client.get(
        f"/v1/organizations/1/stylebooks/{rid}/delete-preview",
        headers=_service_headers(),
    )
    assert pv.status_code == 200
    prev = pv.json()
    assert prev["graphs_referencing"] == 0
    assert prev["is_only_stylebook_in_org"] is False

    bad_del = client.post(
        f"/v1/organizations/1/stylebooks/{rid}/delete",
        headers=_service_headers(),
        json={"confirm_name": "Wrong"},
    )
    assert bad_del.status_code == 400

    ok_del = client.post(
        f"/v1/organizations/1/stylebooks/{rid}/delete",
        headers=_service_headers(),
        json={"confirm_name": "Regional Updated"},
    )
    assert ok_del.status_code == 204


def test_set_default_switches_org_default(client: TestClient) -> None:
    imported = client.post(
        "/v1/organizations/1/stylebooks",
        headers=_service_headers(),
        json={"name": "Imported Catalog", "is_default": False},
    )
    assert imported.status_code == 200
    imported_id = imported.json()["id"]
    assert imported.json()["is_default"] is False

    before = client.get("/v1/organizations/1/stylebooks", headers=_service_headers()).json()
    old_default_id = next(x["id"] for x in before if x["is_default"])

    set_r = client.post(
        f"/v1/organizations/1/stylebooks/{imported_id}/set-default",
        headers=_service_headers(),
    )
    assert set_r.status_code == 200
    assert set_r.json()["is_default"] is True

    after = client.get("/v1/organizations/1/stylebooks", headers=_service_headers()).json()
    defaults = [x for x in after if x["is_default"]]
    assert len(defaults) == 1
    assert defaults[0]["id"] == imported_id
    old = next(x for x in after if x["id"] == old_default_id)
    assert old["is_default"] is False


def test_set_default_and_delete_default_with_replacement(client: TestClient) -> None:
    r = client.post(
        "/v1/organizations/1/stylebooks",
        headers=_service_headers(),
        json={"name": "Backup Book", "is_default": False},
    )
    assert r.status_code == 200
    bid = r.json()["id"]

    r2 = client.post(
        "/v1/organizations/1/stylebooks",
        headers=_service_headers(),
        json={"name": "Primary New", "is_default": True},
    )
    assert r2.status_code == 200
    primary_id = r2.json()["id"]
    assert r2.json()["is_default"] is True

    # Default is now "Primary New"; delete it with replacement Backup Book
    prev = client.get(
        f"/v1/organizations/1/stylebooks/{primary_id}/delete-preview",
        headers=_service_headers(),
    )
    assert prev.status_code == 200
    assert prev.json()["is_default"] is True

    del_r = client.post(
        f"/v1/organizations/1/stylebooks/{primary_id}/delete",
        headers=_service_headers(),
        json={
            "confirm_name": "Primary New",
            "replacement_default_id": bid,
        },
    )
    assert del_r.status_code == 204

    rows = client.get("/v1/organizations/1/stylebooks", headers=_service_headers()).json()
    default_rows = [x for x in rows if x["is_default"]]
    assert len(default_rows) == 1
    assert default_rows[0]["id"] == bid


def test_delete_default_without_replacement_rejected(client: TestClient) -> None:
    r = client.post(
        "/v1/organizations/1/stylebooks",
        headers=_service_headers(),
        json={"name": "Extra"},
    )
    assert r.status_code == 200
    lst2 = client.get("/v1/organizations/1/stylebooks", headers=_service_headers()).json()
    default_row = next(x for x in lst2 if x["is_default"])
    dr = client.post(
        f"/v1/organizations/1/stylebooks/{default_row['id']}/delete",
        headers=_service_headers(),
        json={"confirm_name": default_row["name"]},
    )
    assert dr.status_code == 400
    assert "default" in dr.json()["detail"].lower()
