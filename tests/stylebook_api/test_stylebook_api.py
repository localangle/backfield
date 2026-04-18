"""Integration-style tests for Stylebook API (no Docker)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    Stylebook,
    StylebookLocationCanonical,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select
from stylebook_api.deps import get_session
from stylebook_api.main import app


@pytest.fixture
def _stylebook_test_stack(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> Generator[tuple[TestClient, Engine], None, None]:
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
        s.add(
            BackfieldProject(
                organization_id=oid,
                name="No workspace",
                slug="no-ws-proj",
                workspace_id=None,
            )
        )
        s.commit()

    def get_test_session() -> Generator[Session, None, None]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    client = TestClient(app)
    try:
        yield client, engine
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def client(_stylebook_test_stack: tuple[TestClient, Engine]) -> TestClient:
    return _stylebook_test_stack[0]


@pytest.fixture
def stylebook_test_engine(_stylebook_test_stack: tuple[TestClient, Engine]) -> Engine:
    return _stylebook_test_stack[1]


def _service_headers() -> dict[str, str]:
    return {"Authorization": "Bearer backfield-dev"}


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
        headers=_service_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("lat") is not None


def test_list_stylebooks_service(client: TestClient) -> None:
    r = client.get(
        "/v1/organizations/1/stylebooks",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["slug"] == "default"


def test_list_locations_requires_auth(client: TestClient) -> None:
    r = client.get("/v1/locations?project_slug=demo-proj")
    assert r.status_code == 401


def test_list_locations_empty_with_service_token(client: TestClient) -> None:
    r = client.get(
        "/v1/locations?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["locations"] == []


def test_candidates_400_when_project_has_no_workspace(client: TestClient) -> None:
    r = client.get(
        "/v1/candidates?project_slug=no-ws-proj&status=open",
        headers=_service_headers(),
    )
    assert r.status_code == 400


def test_candidates_open_queue_empty(client: TestClient) -> None:
    r = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 0
    assert data["candidates"] == []


def test_candidates_lists_unlinked_substrate(
    client: TestClient, stylebook_test_engine: object
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        loc = SubstrateLocation(
            project_id=pid,
            name="Chicago",
            normalized_name="chicago",
            location_type="city",
            identity_fingerprint="fp-chicago-1",
            stylebook_location_canonical_id=None,
        )
        s.add(loc)
        s.commit()

    r = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["candidates"][0]["suggested_name"] == "Chicago"


def test_candidates_needs_review_facet(
    client: TestClient, stylebook_test_engine: object
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        loc = SubstrateLocation(
            project_id=pid,
            name="Reviewville",
            normalized_name="reviewville",
            location_type="city",
            identity_fingerprint="fp-review-1",
            stylebook_location_canonical_id=None,
        )
        s.add(loc)
        s.flush()
        lid = int(loc.id)  # type: ignore[arg-type]
        art = SubstrateArticle(
            project_id=pid,
            headline="H",
            text="t",
            url="https://example.com/a1",
        )
        s.add(art)
        s.flush()
        aid = int(art.id)  # type: ignore[arg-type]
        s.add(
            SubstrateLocationMention(
                article_id=aid,
                location_id=lid,
                needs_review=True,
                deleted=False,
            )
        )
        s.commit()

    r_all = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open",
        headers=_service_headers(),
    )
    assert r_all.status_code == 200
    assert r_all.json()["total"] == 1

    r_facet = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open&needs_review=true",
        headers=_service_headers(),
    )
    assert r_facet.status_code == 200
    assert r_facet.json()["total"] == 1
    assert r_facet.json()["candidates"][0]["suggested_name"] == "Reviewville"

    r_open = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open&needs_review=false",
        headers=_service_headers(),
    )
    assert r_open.status_code == 200
    assert r_open.json()["total"] == 1


def test_accept_candidate_create_new(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        loc = SubstrateLocation(
            project_id=pid,
            name="Newplace",
            normalized_name="newplace",
            location_type="city",
            identity_fingerprint="fp-new-1",
            stylebook_location_canonical_id=None,
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]

    r = client.post(
        f"/v1/candidates/{sid}/accept?project_slug=demo-proj",
        headers=_service_headers(),
        json={"create_new": True, "name": "Newplace Canon"},
    )
    assert r.status_code == 200
    assert r.json() == {"message": "linked"}

    with Session(engine) as s:
        row = s.get(SubstrateLocation, sid)
        assert row is not None
        assert row.stylebook_location_canonical_id is not None
        canon = s.get(StylebookLocationCanonical, int(row.stylebook_location_canonical_id))
        assert canon is not None
        assert canon.label == "Newplace Canon"
        assert canon.primary_substrate_location_id is None


def test_accept_candidate_link_existing_canonical(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Existing",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.commit()
        s.refresh(canon)
        cid = int(canon.id)  # type: ignore[arg-type]

        loc = SubstrateLocation(
            project_id=int(proj.id),
            name="Linkme",
            normalized_name="linkme",
            location_type="city",
            identity_fingerprint="fp-link-1",
            stylebook_location_canonical_id=None,
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]

    r = client.post(
        f"/v1/candidates/{sid}/accept?project_slug=demo-proj",
        headers=_service_headers(),
        json={"create_new": False, "stylebook_location_id": cid},
    )
    assert r.status_code == 200

    with Session(engine) as s:
        row = s.get(SubstrateLocation, sid)
        assert row is not None
        assert int(row.stylebook_location_canonical_id or 0) == cid


def test_list_location_mentions_includes_article_and_occurrence_quote(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        loc = SubstrateLocation(
            project_id=pid,
            name="Windy City",
            normalized_name="windy city",
            location_type="city",
            identity_fingerprint="fp-mentions-1",
            stylebook_location_canonical_id=None,
        )
        s.add(loc)
        s.flush()
        lid = int(loc.id)  # type: ignore[arg-type]
        art = SubstrateArticle(
            project_id=pid,
            headline="Chicago story",
            text="We visited Chicago skyline today.",
            url="https://example.com/chicago-story",
        )
        s.add(art)
        s.flush()
        aid = int(art.id)  # type: ignore[arg-type]
        men = SubstrateLocationMention(
            article_id=aid,
            location_id=lid,
            role_in_story="setting",
            nature="primary",
            needs_review=False,
            deleted=False,
        )
        s.add(men)
        s.flush()
        mid = int(men.id)  # type: ignore[arg-type]
        s.add(
            SubstrateLocationMentionOccurrence(
                location_mention_id=mid,
                mention_text="Chicago skyline",
                suppressed=False,
                occurrence_order=0,
            )
        )
        s.commit()

    r = client.get(
        f"/v1/locations/{lid}/mentions?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 1
    assert data["canonical_location_id"] == lid
    assert len(data["mentions"]) == 1
    m0 = data["mentions"][0]
    assert m0["mention_id"] == mid
    assert m0["article_id"] == aid
    assert m0["article_headline"] == "Chicago story"
    assert m0["article_url"] == "https://example.com/chicago-story"
    assert m0["original_text"] == "Chicago skyline"
    assert m0["description"] == "setting"
