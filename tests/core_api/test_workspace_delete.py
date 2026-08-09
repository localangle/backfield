"""Core API workspace delete-preview / typed-name delete."""

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
from sqlmodel import Session, SQLModel, create_engine, select

from tests.core_api.auth_helpers import attach_test_engine, seed_and_login
from tests.integration_helpers import patch_test_engine
from tests.project_helpers import project_ownership_fields


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("SERVICE_API_TOKEN", "backfield-dev")
    import importlib

    import backfield_auth.service_tokens as service_tokens

    importlib.reload(service_tokens)

    database_path = tmp_path / "core-workspace-delete.db"
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
        oid = int(org.id)
        sb = ensure_default_stylebook_for_organization(s, oid)
        sb_id = int(sb.id)  # type: ignore[arg-type]
        keep = BackfieldWorkspace(
            organization_id=oid,
            stylebook_id=sb_id,
            name="Keep Workspace",
            slug="keep",
        )
        s.add(keep)
        s.commit()
        s.refresh(keep)
        doomed = BackfieldWorkspace(
            organization_id=oid,
            stylebook_id=sb_id,
            name="Doomed Workspace",
            slug="doomed",
        )
        s.add(doomed)
        s.commit()
        s.refresh(doomed)
        s.add(
            BackfieldProject(
                **project_ownership_fields(s, oid, workspace_id=int(doomed.id)),
                organization_id=oid,
                workspace_id=int(doomed.id),
                name="Alpha",
                slug="alpha",
            )
        )
        s.add(
            BackfieldProject(
                **project_ownership_fields(s, oid, workspace_id=int(doomed.id)),
                organization_id=oid,
                workspace_id=int(doomed.id),
                name="Beta",
                slug="beta",
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


def _doomed_workspace_id(client: TestClient) -> int:
    dependency = app.dependency_overrides[get_session]
    gen = dependency()
    session = next(gen)
    try:
        row = session.exec(
            select(BackfieldWorkspace).where(BackfieldWorkspace.slug == "doomed")
        ).first()
        assert row is not None and row.id is not None
        return int(row.id)
    finally:
        gen.close()


def test_workspace_delete_preview_and_confirm(client: TestClient) -> None:
    seed_and_login(client, "admin@example.com", "admin-secret-12")
    wid = _doomed_workspace_id(client)

    preview = client.get(f"/v1/organizations/1/workspaces/{wid}/delete-preview")
    assert preview.status_code == 200
    body = preview.json()
    assert body["name"] == "Doomed Workspace"
    assert body["project_count"] == 2
    assert {p["slug"] for p in body["projects"]} == {"alpha", "beta"}

    wrong = client.post(
        f"/v1/organizations/1/workspaces/{wid}/delete",
        json={"confirm_name": "Wrong"},
    )
    assert wrong.status_code == 400

    ok = client.post(
        f"/v1/organizations/1/workspaces/{wid}/delete",
        json={"confirm_name": "Doomed Workspace"},
    )
    assert ok.status_code == 204

    listed = client.get("/v1/organizations/1/workspaces")
    assert listed.status_code == 200
    slugs = {w["slug"] for w in listed.json()}
    assert "doomed" not in slugs
    assert "keep" in slugs


def test_workspace_delete_requires_org_admin(client: TestClient) -> None:
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

    wid = _doomed_workspace_id(client)
    r = client.post(
        f"/v1/organizations/1/workspaces/{wid}/delete",
        json={"confirm_name": "Doomed Workspace"},
    )
    assert r.status_code == 403
