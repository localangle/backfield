"""Tests for Stylebook cleanup API routes."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldUser,
    Stylebook,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select
from stylebook_api.deps import get_auth as get_auth_dep
from stylebook_api.deps import get_session
from stylebook_api.main import app


def _session_auth_for_user(user: BackfieldUser, *, org_id: int) -> dict[str, Any]:
    return {
        "type": "session",
        "user": user,
        "token_data": {},
        "organization_id": int(org_id),
        "org_role": "org_admin",
        "is_admin": True,
    }


@pytest.fixture
def cleanup_client(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[TestClient, Engine], None, None]:
    monkeypatch.setenv("SERVICE_API_TOKEN", "backfield-dev")
    monkeypatch.setattr(
        "stylebook_api.semantic_reindex.celery_app.send_task",
        lambda *_args, **_kwargs: None,
    )
    import importlib

    import backfield_auth.service_tokens as service_tokens

    importlib.reload(service_tokens)

    database_path = tmp_path / "stylebook-cleanup-test.db"
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
        org_id = int(org.id)
        user = BackfieldUser(email="admin@example.com", password_hash="x")
        s.add(user)
        s.commit()
        s.refresh(user)
        sb = Stylebook(
            organization_id=org_id,
            slug="default",
            name="Default Stylebook",
            is_default=True,
        )
        s.add(sb)
        s.commit()
        s.refresh(sb)
        sb_id = int(sb.id)
        s.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="dupe-a",
                label="Ward 36, Chicago, IL",
            )
        )
        s.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="dupe-b",
                label="Ward 36, Chicago, IL",
            )
        )
        s.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="fuzzy-a",
                label="Billy Goat Tavern, Chicago, IL",
            )
        )
        s.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="fuzzy-b",
                label="Billy Goat Tavern, West Loop, Chicago, IL",
            )
        )
        s.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="unique-chicago",
                label="Near West Side, Chicago, IL",
            )
        )
        s.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="missing-geom",
                label="No map pin here",
            )
        )
        s.add(
            StylebookLocationCanonical(
                stylebook_id=sb_id,
                slug="has-geom",
                label="Mapped place",
                geometry_json={"type": "Point", "coordinates": [-87.6, 41.8]},
            )
        )
        s.commit()
        user_id = int(user.id)

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    def get_test_auth() -> dict[str, Any]:
        with Session(engine) as session:
            u = session.get(BackfieldUser, user_id)
            assert u is not None
            return _session_auth_for_user(u, org_id=org_id)

    app.dependency_overrides[get_session] = get_test_session
    app.dependency_overrides[get_auth_dep] = get_test_auth
    client = TestClient(app)
    try:
        yield client, engine
    finally:
        app.dependency_overrides.clear()


def test_list_cleanup_checks(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, _engine = cleanup_client
    r = client.get("/v1/stylebooks/default/cleanup/checks")
    assert r.status_code == 200
    body = r.json()
    assert "checks" in body
    ids = {check["id"] for check in body["checks"]}
    assert ids == {"duplicate-locations", "missing-geometry-locations"}
    by_id = {check["id"]: check["count"] for check in body["checks"]}
    assert by_id["duplicate-locations"] == 2
    assert by_id["missing-geometry-locations"] == 6
    assert body["total_open"] == by_id["duplicate-locations"] + by_id["missing-geometry-locations"]


def test_duplicate_location_clusters(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, _engine = cleanup_client
    r = client.get("/v1/stylebooks/default/cleanup/checks/duplicate-locations?limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    labels = {cluster["label"] for cluster in body["clusters"]}
    assert "Ward 36, Chicago, IL" in labels
    assert "Billy Goat Tavern" in labels


def test_missing_geometry_locations(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, _engine = cleanup_client
    r = client.get("/v1/stylebooks/default/cleanup/checks/missing-geometry-locations")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 6
    labels = {item["label"] for item in body["canonicals"]}
    assert "No map pin here" in labels


def test_delete_empty_cleanup_canonical(cleanup_client: tuple[TestClient, Engine]) -> None:
    client, engine = cleanup_client
    with Session(engine) as session:
        empty = session.exec(
            select(StylebookLocationCanonical).where(
                StylebookLocationCanonical.slug == "missing-geom"
            )
        ).one()
        canonical_id = str(empty.id)
    response = client.delete(
        f"/v1/stylebooks/default/cleanup/canonical-locations/{canonical_id}"
    )
    assert response.status_code == 200
    assert response.json()["id"] == canonical_id
    with Session(engine) as session:
        assert session.get(StylebookLocationCanonical, canonical_id) is None


def test_merge_cleanup_canonical_relinks_and_deletes_source(
    cleanup_client: tuple[TestClient, Engine],
) -> None:
    client, engine = cleanup_client
    with Session(engine) as session:
        org = session.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.slug == "default")
        ).one()
        session.add(
            BackfieldProject(
                organization_id=int(org.id),
                name="Demo",
                slug="demo-proj",
            )
        )
        session.commit()
        proj = session.exec(
            select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")
        ).one()
        source = session.exec(
            select(StylebookLocationCanonical).where(StylebookLocationCanonical.slug == "dupe-a")
        ).one()
        target = session.exec(
            select(StylebookLocationCanonical).where(StylebookLocationCanonical.slug == "dupe-b")
        ).one()
        session.add(
            SubstrateLocation(
                project_id=int(proj.id),
                name="Ward spot",
                normalized_name="ward-spot",
                location_type="place",
                identity_fingerprint="fp-cleanup-merge",
                stylebook_location_canonical_id=str(source.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
            )
        )
        session.commit()
        source_id = str(source.id)
        target_id = str(target.id)

    response = client.post(
        f"/v1/stylebooks/default/cleanup/canonical-locations/{source_id}/merge-into",
        json={"target_canonical_id": target_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["source_id"] == source_id
    assert body["target_id"] == target_id
    assert body["relinked_substrate_count"] == 1
    assert body["source_deleted"] is True

    with Session(engine) as session:
        assert session.get(StylebookLocationCanonical, source_id) is None
        loc = session.exec(
            select(SubstrateLocation).where(
                SubstrateLocation.identity_fingerprint == "fp-cleanup-merge"
            )
        ).one()
        assert loc.stylebook_location_canonical_id == target_id
