"""Agate API project delete-preview / typed-name delete."""

from __future__ import annotations

import json
from collections.abc import Generator
from types import SimpleNamespace
from typing import Any

import pytest
from api.deps import get_auth, get_session
from api.main import app
from backfield_db import (
    AgateGraph,
    AgateProcessedItem,
    AgateRun,
    BackfieldOrganization,
    BackfieldOrganizationMembership,
    BackfieldProject,
    BackfieldUser,
    BackfieldWorkspace,
    SubstrateArticle,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select

from tests.integration_helpers import patch_test_engine
from tests.project_helpers import project_ownership_fields


@pytest.fixture
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setenv("SERVICE_API_TOKEN", "backfield-dev")
    import importlib

    import backfield_auth.service_tokens as service_tokens

    importlib.reload(service_tokens)

    database_path = tmp_path / "agate-project-delete.db"
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
                **project_ownership_fields(s, oid, workspace_id=int(ws.id)),
                organization_id=oid,
                workspace_id=int(ws.id),
                name="General",
                slug="general",
            )
        )
        s.add(
            BackfieldProject(
                **project_ownership_fields(s, oid, workspace_id=int(ws.id)),
                organization_id=oid,
                workspace_id=int(ws.id),
                name="Demo Project",
                slug="demo-project",
            )
        )
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        yield TestClient(
            app,
            headers={
                "Authorization": "Bearer backfield-dev",
                "X-Backfield-Organization-ID": "1",
            },
        )
    finally:
        app.dependency_overrides.clear()


def _demo_project_id(client: TestClient) -> int:
    dependency = app.dependency_overrides[get_session]
    session_generator = dependency()
    session = next(session_generator)
    try:
        row = session.exec(
            select(BackfieldProject).where(BackfieldProject.slug == "demo-project")
        ).first()
        assert row is not None and row.id is not None
        return int(row.id)
    finally:
        session_generator.close()


def _general_project_id(client: TestClient) -> int:
    dependency = app.dependency_overrides[get_session]
    session_generator = dependency()
    session = next(session_generator)
    try:
        row = session.exec(
            select(BackfieldProject).where(BackfieldProject.slug == "general")
        ).first()
        assert row is not None and row.id is not None
        return int(row.id)
    finally:
        session_generator.close()


def test_project_delete_preview_and_confirm(client: TestClient) -> None:
    pid = _demo_project_id(client)
    dependency = app.dependency_overrides[get_session]
    session_generator = dependency()
    session = next(session_generator)
    try:
        graph = AgateGraph(
            name="Flow",
            spec_json=json.dumps({"name": "Flow", "nodes": [], "edges": []}),
            project_id=pid,
        )
        session.add(graph)
        session.commit()
        session.refresh(graph)
        run = AgateRun(graph_id=str(graph.id), status="succeeded")
        session.add(run)
        session.commit()
        session.refresh(run)
        session.add(
            AgateProcessedItem(
                run_id=str(run.id),
                status="succeeded",
                input_json="{}",
                result_json="{}",
            )
        )
        session.add(SubstrateArticle(project_id=pid, headline="H", text="T"))
        session.commit()
    finally:
        session_generator.close()

    preview = client.get(f"/projects/{pid}/delete-preview")
    assert preview.status_code == 200
    body = preview.json()
    assert body["name"] == "Demo Project"
    assert body["flow_count"] == 1
    assert body["processed_item_count"] == 1
    assert body["article_count"] == 1

    wrong = client.post(f"/projects/{pid}/delete", json={"confirm_name": "Wrong"})
    assert wrong.status_code == 400

    ok = client.post(f"/projects/{pid}/delete", json={"confirm_name": "Demo Project"})
    assert ok.status_code == 204

    gone = client.get(f"/projects/{pid}")
    assert gone.status_code == 404


def test_project_delete_blocks_general(client: TestClient) -> None:
    pid = _general_project_id(client)
    r = client.post(f"/projects/{pid}/delete", json={"confirm_name": "General"})
    assert r.status_code == 400
    assert "general" in r.json()["detail"].lower()


def test_project_delete_requires_org_admin(client: TestClient) -> None:
    pid = _demo_project_id(client)
    dependency = app.dependency_overrides[get_session]
    session_generator = dependency()
    session = next(session_generator)
    try:
        user = BackfieldUser(email="member@example.com", password_hash="x")
        session.add(user)
        session.commit()
        session.refresh(user)
        session.add(
            BackfieldOrganizationMembership(
                user_id=int(user.id),
                organization_id=1,
                role="member",
            )
        )
        session.commit()
        uid = int(user.id)
    finally:
        session_generator.close()

    def member_auth() -> dict[str, Any]:
        return {
            "type": "session",
            "user": SimpleNamespace(id=uid),
            "organization_id": 1,
            "org_role": "member",
            "is_admin": False,
        }

    app.dependency_overrides[get_auth] = member_auth
    try:
        r = client.post(f"/projects/{pid}/delete", json={"confirm_name": "Demo Project"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(get_auth, None)
