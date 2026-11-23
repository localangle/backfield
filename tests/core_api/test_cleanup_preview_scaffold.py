"""Scopes, Stylebook resolution, and hiding for the preview cleanup routes."""

from __future__ import annotations

import json
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from backfield_db import BackfieldOrganization, BackfieldProject, BackfieldWorkspace, Stylebook
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from core_api.deps import get_session
from core_api.main import app
from core_api.routers.public.openapi import (
    CLEANUP_PREVIEW_TAG,
    _without_preview_operations,
    build_public_openapi,
)
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from tests.core_api.auth_helpers import attach_test_engine, seed_first_admin
from tests.project_helpers import project_ownership_fields

CAPABILITIES_URL = "/public/v1/projects/general/stylebooks/{slug}/cleanup/capabilities"
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path) -> Generator[TestClient, None, None]:
    engine = create_engine(
        f"sqlite:///{tmp_path / 'cleanup-preview-test.db'}",
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
        ws = BackfieldWorkspace(
            organization_id=oid,
            stylebook_id=int(sb.id),  # type: ignore[arg-type]
            name="Default Workspace",
            slug="default",
        )
        s.add(ws)
        s.commit()
        s.refresh(ws)
        s.add(
            BackfieldProject(
                **project_ownership_fields(s, oid, workspace_id=int(ws.id)),
                name="General",
                slug="general",
                organization_id=oid,
                workspace_id=int(ws.id),
            )
        )
        other_org = BackfieldOrganization(name="Other Org", slug="other-org")
        s.add(other_org)
        s.flush()
        s.add(
            Stylebook(
                organization_id=int(other_org.id),
                slug="foreign-stylebook",
                name="Foreign Stylebook",
                is_default=True,
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


def _create_key(client: TestClient, *, credential_type: str, scopes: list[str]) -> dict[str, str]:
    seed_first_admin(client, "cleanup-admin@example.com", "cleanup-secret")
    client.post(
        "/v1/auth/login",
        json={"email": "cleanup-admin@example.com", "password": "cleanup-secret"},
    )
    created = client.post(
        "/v1/projects/1/api-keys",
        json={"credential_type": credential_type, "scopes": scopes},
    )
    assert created.status_code == 200
    return {"Authorization": f"Bearer {created.json()['raw_key']}"}


def test_capabilities_requires_cleanup_read(client: TestClient) -> None:
    headers = _create_key(client, credential_type="user", scopes=[])
    r = client.get(CAPABILITIES_URL.format(slug="default"), headers=headers)
    assert r.status_code == 403
    assert "cleanup:read" in r.json()["error"]["message"]


def test_capabilities_for_read_only_key(client: TestClient) -> None:
    headers = _create_key(client, credential_type="user", scopes=["cleanup:read"])
    r = client.get(CAPABILITIES_URL.format(slug="default"), headers=headers)
    assert r.status_code == 200
    assert r.json() == {
        "contract_version": "preview-1",
        "stylebook_slug": "default",
        "scopes": ["read", "cleanup:read"],
        "can_apply": False,
    }


def test_capabilities_for_apply_key(client: TestClient) -> None:
    headers = _create_key(client, credential_type="service", scopes=["cleanup:apply"])
    r = client.get(CAPABILITIES_URL.format(slug="default"), headers=headers)
    assert r.status_code == 200
    assert r.json()["can_apply"] is True


def test_capabilities_rejects_unknown_and_foreign_stylebooks(client: TestClient) -> None:
    headers = _create_key(client, credential_type="user", scopes=["cleanup:read"])
    for slug in ("no-such-stylebook", "foreign-stylebook"):
        r = client.get(CAPABILITIES_URL.format(slug=slug), headers=headers)
        assert r.status_code == 404, slug


def test_published_contract_has_no_cleanup_routes(client: TestClient) -> None:
    published = client.get("/public/v1/openapi.json").json()
    assert not [path for path in published["paths"] if "/cleanup" in path]

    committed = json.loads((REPO_ROOT / "docs/api/public.openapi.json").read_text())
    assert not [path for path in committed["paths"] if "/cleanup" in path]


def test_app_schema_still_lists_cleanup_routes() -> None:
    schema = app.openapi()
    path = "/public/v1/projects/{project_slug}/stylebooks/{stylebook_slug}/cleanup/capabilities"
    assert path in schema["paths"]
    assert CLEANUP_PREVIEW_TAG in schema["paths"][path]["get"]["tags"]
    assert path not in build_public_openapi(schema)["paths"]


def test_preview_filter_keeps_untagged_operations_and_drops_empty_paths() -> None:
    mixed: dict[str, Any] = {
        "parameters": [{"name": "x"}],
        "get": {"tags": ["public"]},
        "post": {"tags": ["public", CLEANUP_PREVIEW_TAG]},
    }
    kept = _without_preview_operations(mixed)
    assert kept is not None and "get" in kept and "post" not in kept
    assert kept["parameters"] == [{"name": "x"}]

    only_preview: dict[str, Any] = {"get": {"tags": [CLEANUP_PREVIEW_TAG]}}
    assert _without_preview_operations(only_preview) is None
