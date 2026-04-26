"""Integration-style tests for Stylebook API (no Docker)."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    Stylebook,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from backfield_stylebook.canonical_link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_UNLINKED,
    CANONICAL_LINK_WAIVED,
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


def test_create_location_creates_standalone_canonical_and_alias_no_substrate(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        q = select(SubstrateLocation).where(SubstrateLocation.project_id == pid)
        before = len(s.exec(q).all())

    r = client.post(
        "/v1/locations?project_slug=demo-proj",
        headers=_service_headers(),
        json={
            "name": "West Garfield Park, Chicago, IL",
            "location_type": "neighborhood",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "West Garfield Park, Chicago, IL"
    assert body.get("location_type") == "neighborhood"
    cid = int(body["id"])
    assert body.get("linked_substrate_count", 0) == 0
    with Session(stylebook_test_engine) as s:
        q2 = select(SubstrateLocation).where(SubstrateLocation.project_id == pid)
        after = len(s.exec(q2).all())
        assert after == before
        canon = s.get(StylebookLocationCanonical, cid)
        assert canon is not None
        assert canon.label == "West Garfield Park, Chicago, IL"
        assert canon.location_type == "neighborhood"
        aliases = s.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == cid,
            )
        ).all()
        assert len(aliases) == 1
        assert aliases[0].normalized_alias == "west garfield park, chicago, il"


def test_create_canonical_location_post_alias_no_substrate(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        q0 = select(SubstrateLocation).where(SubstrateLocation.project_id == pid)
        before = len(s.exec(q0).all())

    r = client.post(
        "/v1/canonical-locations?project_slug=demo-proj",
        headers=_service_headers(),
        json={"label": "Solo Canonical, Evanston, IL"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "Solo Canonical, Evanston, IL"
    cid = int(body["id"])
    with Session(stylebook_test_engine) as s:
        canon = s.get(StylebookLocationCanonical, cid)
        assert canon is not None
        q1 = select(SubstrateLocation).where(SubstrateLocation.project_id == pid)
        after = len(s.exec(q1).all())
        assert after == before


def test_list_canonical_locations_type_filter(client: TestClient) -> None:
    r_city = client.post(
        "/v1/canonical-locations?project_slug=demo-proj",
        headers=_service_headers(),
        json={"label": "Filter City Row", "location_type": "city"},
    )
    assert r_city.status_code == 200
    r_nb = client.post(
        "/v1/canonical-locations?project_slug=demo-proj",
        headers=_service_headers(),
        json={"label": "Filter Neighborhood Row", "location_type": "neighborhood"},
    )
    assert r_nb.status_code == 200
    r_list = client.get(
        "/v1/canonical-locations?project_slug=demo-proj&type_filter=city",
        headers=_service_headers(),
    )
    assert r_list.status_code == 200
    data = r_list.json()
    labels = {c["label"] for c in data["canonicals"]}
    assert "Filter City Row" in labels
    assert "Filter Neighborhood Row" not in labels
    for row in data["canonicals"]:
        if row["label"] == "Filter City Row":
            assert row.get("location_type") == "city"
    r_bad = client.get(
        "/v1/canonical-locations?project_slug=demo-proj&type_filter=not_a_real_type",
        headers=_service_headers(),
    )
    assert r_bad.status_code == 400


def test_list_canonical_locations_orders_by_label_case_insensitive(client: TestClient) -> None:
    for label in ("Zebra", "alpha", "Mike"):
        r = client.post(
            "/v1/canonical-locations?project_slug=demo-proj",
            headers=_service_headers(),
            json={"label": label},
        )
        assert r.status_code == 200
    r = client.get(
        "/v1/canonical-locations?project_slug=demo-proj&limit=50",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    labels = [c["label"] for c in r.json()["canonicals"]]
    assert labels == ["alpha", "Mike", "Zebra"]


def test_list_canonical_locations_search_prefers_exact_then_prefix_then_contains(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    _ = stylebook_test_engine
    from urllib.parse import quote

    # Contiguous substring filter: every row must contain the full query text.
    exact_query = "CanonSearchToken Chicago, IL"
    a = f"{exact_query} Extra Words"
    b = exact_query
    c = f"{exact_query} More"
    for lb in (a, b, c):
        r = client.post(
            "/v1/canonical-locations?project_slug=demo-proj",
            headers=_service_headers(),
            json={"label": lb},
        )
        assert r.status_code == 200

    q = quote(exact_query)
    r = client.get(
        f"/v1/canonical-locations?project_slug=demo-proj&q={q}&limit=200",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    labels = [row["label"] for row in r.json()["canonicals"]]
    assert a in labels and b in labels and c in labels
    assert labels.index(b) < labels.index(a)
    assert labels.index(b) < labels.index(c)

    prefix_query = "CanonSearchToken2 Chicago"
    a2 = f"Albany, {prefix_query}, IL"
    b2 = f"{prefix_query}, IL"
    c2 = f"United, {prefix_query}, IL"
    for lb in (a2, b2, c2):
        r = client.post(
            "/v1/canonical-locations?project_slug=demo-proj",
            headers=_service_headers(),
            json={"label": lb},
        )
        assert r.status_code == 200

    q2 = quote(prefix_query)
    r2 = client.get(
        f"/v1/canonical-locations?project_slug=demo-proj&q={q2}&limit=200",
        headers=_service_headers(),
    )
    assert r2.status_code == 200
    labels2 = [row["label"] for row in r2.json()["canonicals"]]
    assert a2 in labels2 and b2 in labels2 and c2 in labels2
    assert labels2.index(b2) < labels2.index(a2)
    assert labels2.index(b2) < labels2.index(c2)


def test_list_canonical_locations_returns_catalog_not_substrate(client: TestClient) -> None:
    r = client.post(
        "/v1/locations?project_slug=demo-proj",
        headers=_service_headers(),
        json={"name": "Catalog Test Place", "location_type": "city"},
    )
    assert r.status_code == 200
    created = r.json()
    canon_fk = int(created["id"])
    assert created["label"] == "Catalog Test Place"
    r2 = client.get("/v1/canonical-locations?project_slug=demo-proj", headers=_service_headers())
    assert r2.status_code == 200
    data = r2.json()
    assert data["total"] >= 1
    canon = next(c for c in data["canonicals"] if c["label"] == "Catalog Test Place")
    assert int(canon["id"]) == int(canon_fk)
    assert canon.get("linked_substrate_count", 0) == 0
    r3 = client.get(
        f"/v1/canonical-locations/{canon['id']}?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r3.status_code == 200
    assert r3.json()["label"] == "Catalog Test Place"


def test_patch_canonical_location_updates_location_type_and_formatted_address(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    _ = stylebook_test_engine
    r = client.post(
        "/v1/canonical-locations?project_slug=demo-proj",
        headers=_service_headers(),
        json={"label": "Patchable Canon Row"},
    )
    assert r.status_code == 200
    cid = int(r.json()["id"])
    r2 = client.patch(
        f"/v1/canonical-locations/{cid}?project_slug=demo-proj",
        headers=_service_headers(),
        json={"location_type": "city", "formatted_address": "Patchable, IL, USA"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["location_type"] == "city"
    assert body["formatted_address"] == "Patchable, IL, USA"
    r3 = client.get(
        f"/v1/canonical-locations/{cid}?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r3.status_code == 200
    assert r3.json()["location_type"] == "city"
    assert r3.json()["formatted_address"] == "Patchable, IL, USA"
    r4 = client.patch(
        f"/v1/canonical-locations/{cid}?project_slug=demo-proj",
        headers=_service_headers(),
        json={"location_type": None, "formatted_address": None},
    )
    assert r4.status_code == 200
    cleared = r4.json()
    assert cleared.get("location_type") is None
    assert cleared.get("formatted_address") is None


def test_stats_locations_initial_zeros(client: TestClient) -> None:
    r = client.get("/v1/stats?project_slug=demo-proj", headers=_service_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["locations"]["canonical_count"] == 0
    assert body["locations"]["candidate_count"] == 0
    assert body["people"]["canonical_count"] == 0


def test_stats_no_workspace_project_returns_location_zeros(client: TestClient) -> None:
    r = client.get("/v1/stats?project_slug=no-ws-proj", headers=_service_headers())
    assert r.status_code == 200
    loc = r.json()["locations"]
    assert loc["canonical_count"] == 0
    assert loc["candidate_count"] == 0


def test_stats_reflects_canonical_and_pending_candidates(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    r_loc = client.post(
        "/v1/locations?project_slug=demo-proj",
        headers=_service_headers(),
        json={"name": "Stats Town", "location_type": "city"},
    )
    assert r_loc.status_code == 200
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        s.add(
            SubstrateLocation(
                project_id=pid,
                name="Pending One",
                normalized_name="pending-one",
                location_type="city",
                identity_fingerprint="fp-stats-p1",
                stylebook_location_canonical_id=None,
                canonical_link_status=CANONICAL_LINK_PENDING,
            )
        )
        s.add(
            SubstrateLocation(
                project_id=pid,
                name="Pending Two",
                normalized_name="pending-two",
                location_type="city",
                identity_fingerprint="fp-stats-p2",
                stylebook_location_canonical_id=None,
                canonical_link_status=CANONICAL_LINK_PENDING,
            )
        )
        s.commit()

    r = client.get("/v1/stats?project_slug=demo-proj", headers=_service_headers())
    assert r.status_code == 200
    loc = r.json()["locations"]
    assert loc["canonical_count"] == 1
    assert loc["candidate_count"] == 2


def test_candidates_types_returns_place_extract_taxonomy(client: TestClient) -> None:
    r = client.get(
        "/v1/candidates/types?project_slug=demo-proj&status=open",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    types = r.json()["types"]
    assert types[0] == "place"
    assert "city" in types
    assert "intersection_road" in types
    assert types[-1] == "other"
    assert len(types) == 16


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


def test_candidates_defer_removes_from_open_queue_and_lists_in_deferred(
    client: TestClient, stylebook_test_engine: object
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        loc = SubstrateLocation(
            project_id=pid,
            name="Deferme",
            normalized_name="deferme",
            location_type="city",
            identity_fingerprint="fp-defer-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]

    r0 = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open",
        headers=_service_headers(),
    )
    assert r0.status_code == 200
    assert r0.json()["total"] == 1

    r_def = client.post(
        f"/v1/candidates/{sid}/defer?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r_def.status_code == 200
    assert r_def.json() == {"message": "deferred"}

    r1 = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open",
        headers=_service_headers(),
    )
    assert r1.status_code == 200
    assert r1.json()["total"] == 0

    r2 = client.get(
        "/v1/candidates?project_slug=demo-proj&status=deferred",
        headers=_service_headers(),
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["total"] == 1
    assert body["candidates"][0]["suggested_name"] == "Deferme"
    assert body["candidates"][0]["status"] == "deferred"

    with Session(engine) as s:
        row = s.get(SubstrateLocation, sid)
        assert row is not None
        assert row.stylebook_location_canonical_id is None
        assert row.canonical_link_status == CANONICAL_LINK_WAIVED


def test_deferred_candidate_lists_defer_display_message_from_reasons_json(
    client: TestClient, stylebook_test_engine: object
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        loc = SubstrateLocation(
            project_id=pid,
            name="Private Rd",
            normalized_name="private rd",
            location_type="address",
            identity_fingerprint="fp-private-msg-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_WAIVED,
            canonical_review_reasons_json=[
                {
                    "code": "private_place_or_residence",
                    "message": "Private place or residence",
                    "location_type": "address",
                }
            ],
        )
        s.add(loc)
        s.commit()

    r = client.get(
        "/v1/candidates?project_slug=demo-proj&status=deferred",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    cand = body["candidates"][0]
    assert cand["suggested_name"] == "Private Rd"
    assert cand["defer_display_message"] == "Private place or residence"


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
            canonical_link_status=CANONICAL_LINK_PENDING,
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


def test_candidates_filters_by_q_and_type_filter(
    client: TestClient, stylebook_test_engine: object
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        s.add(
            SubstrateLocation(
                project_id=pid,
                name="Chicago",
                normalized_name="chicago",
                location_type="city",
                identity_fingerprint="fp-chicago-filter",
                stylebook_location_canonical_id=None,
                canonical_link_status=CANONICAL_LINK_PENDING,
            )
        )
        s.add(
            SubstrateLocation(
                project_id=pid,
                name="Wicker Park",
                normalized_name="wicker park",
                location_type="neighborhood",
                identity_fingerprint="fp-wicker-filter",
                stylebook_location_canonical_id=None,
                canonical_link_status=CANONICAL_LINK_PENDING,
            )
        )
        s.commit()

    r_q = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open&q=wicker",
        headers=_service_headers(),
    )
    assert r_q.status_code == 200
    assert r_q.json()["total"] == 1
    assert r_q.json()["candidates"][0]["suggested_name"] == "Wicker Park"

    r_t = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open&type_filter=city",
        headers=_service_headers(),
    )
    assert r_t.status_code == 200
    assert r_t.json()["total"] == 1
    assert r_t.json()["candidates"][0]["suggested_name"] == "Chicago"


def test_candidates_open_queue_sorted_by_normalized_name(
    client: TestClient, stylebook_test_engine: object
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        s.add(
            SubstrateLocation(
                project_id=pid,
                name="SortTest B",
                normalized_name="sorttest b",
                location_type="city",
                identity_fingerprint="fp-sorttest-b",
                stylebook_location_canonical_id=None,
                canonical_link_status=CANONICAL_LINK_PENDING,
            )
        )
        s.add(
            SubstrateLocation(
                project_id=pid,
                name="SortTest A",
                normalized_name="sorttest a",
                location_type="city",
                identity_fingerprint="fp-sorttest-a",
                stylebook_location_canonical_id=None,
                canonical_link_status=CANONICAL_LINK_PENDING,
            )
        )
        s.commit()

    r = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open&q=SortTest",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    names = [c["suggested_name"] for c in r.json()["candidates"]]
    assert "SortTest A" in names and "SortTest B" in names
    assert names.index("SortTest A") < names.index("SortTest B")


def test_candidates_q_matches_normalized_name_when_display_name_differs(
    client: TestClient, stylebook_test_engine: object
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        s.add(
            SubstrateLocation(
                project_id=pid,
                name="Display Only",
                normalized_name="normmatchunique chicago il",
                location_type="city",
                identity_fingerprint="fp-normmatchunique",
                stylebook_location_canonical_id=None,
                canonical_link_status=CANONICAL_LINK_PENDING,
            )
        )
        s.commit()

    r = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open&q=normmatchunique",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 1
    assert any(c["suggested_name"] == "Display Only" for c in r.json()["candidates"])


def test_candidate_context_and_note_roundtrip(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        art = SubstrateArticle(
            project_id=pid,
            headline="H",
            text="We visited Chicago skyline today.",
            url="https://example.com/a2",
            deleted=False,
        )
        s.add(art)
        s.flush()
        aid = int(art.id)  # type: ignore[arg-type]
        loc = SubstrateLocation(
            project_id=pid,
            name="Chicago",
            normalized_name="chicago",
            location_type="city",
            identity_fingerprint="fp-chicago-ctx",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        s.add(loc)
        s.flush()
        lid = int(loc.id)  # type: ignore[arg-type]
        men = SubstrateLocationMention(
            article_id=aid,
            location_id=lid,
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
                quote_text="We visited Chicago skyline today.",
                suppressed=False,
                occurrence_order=0,
            )
        )
        s.commit()

    r0 = client.get(
        f"/v1/candidates/{lid}/context?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r0.status_code == 200
    body = r0.json()
    assert body["substrate_location_id"] == lid
    assert body["created_at"] is not None
    assert body["examples"]
    assert "Chicago skyline" in body["examples"][0]["text"]

    r1 = client.post(
        f"/v1/candidates/{lid}/note?project_slug=demo-proj",
        headers=_service_headers(),
        json={"note": "Ambiguous between city and sports team."},
    )
    assert r1.status_code == 200

    r2 = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open&q=chicago",
        headers=_service_headers(),
    )
    assert r2.status_code == 200
    row = r2.json()["candidates"][0]
    assert row["created_at"] is not None
    assert row["note"] == "Ambiguous between city and sports team."


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
            canonical_link_status=CANONICAL_LINK_PENDING,
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
            formatted_address="Newplace, IL, USA",
            identity_fingerprint="fp-new-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
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
    data = r.json()
    assert data["message"] == "linked"
    assert "stylebook_location_canonical_id" in data

    with Session(engine) as s:
        row = s.get(SubstrateLocation, sid)
        assert row is not None
        assert row.stylebook_location_canonical_id is not None
        assert row.canonical_link_status == CANONICAL_LINK_LINKED
        canon = s.get(StylebookLocationCanonical, int(row.stylebook_location_canonical_id))
        assert canon is not None
        coid = int(canon.id)  # type: ignore[arg-type]
        assert int(data["stylebook_location_canonical_id"]) == coid
        assert row.canonical_review_reasons_json == [
            {"code": "linked_manual_accept_create_new", "canonical_id": coid}
        ]
        assert canon.label == "Newplace Canon"
        assert canon.location_type == "city"
        assert canon.formatted_address == "Newplace, IL, USA"
        assert canon.primary_substrate_location_id is None
        canon_id = int(canon.id)  # type: ignore[arg-type]
        aliases = s.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == canon_id,
            )
        ).all()
        assert len(aliases) == 1
        assert aliases[0].normalized_alias == "newplace"


def test_accept_candidate_create_new_location_type_override(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        loc = SubstrateLocation(
            project_id=pid,
            name="TypoTown",
            normalized_name="typotown",
            location_type="city",
            formatted_address="TypoTown, IL, USA",
            identity_fingerprint="fp-type-override-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]

    r = client.post(
        f"/v1/candidates/{sid}/accept?project_slug=demo-proj",
        headers=_service_headers(),
        json={"create_new": True, "name": "TypoTown Canon", "location_type": "neighborhood"},
    )
    assert r.status_code == 200

    with Session(engine) as s:
        row = s.get(SubstrateLocation, sid)
        assert row is not None
        assert row.stylebook_location_canonical_id is not None
        canon = s.get(StylebookLocationCanonical, int(row.stylebook_location_canonical_id))
        assert canon is not None
        assert canon.label == "TypoTown Canon"
        assert canon.location_type == "neighborhood"


def test_accept_candidate_create_new_rejects_invalid_location_type(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        loc = SubstrateLocation(
            project_id=pid,
            name="BadType",
            normalized_name="badtype",
            location_type="city",
            identity_fingerprint="fp-bad-type-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]

    r = client.post(
        f"/v1/candidates/{sid}/accept?project_slug=demo-proj",
        headers=_service_headers(),
        json={"create_new": True, "name": "X", "location_type": "not_a_placeextract_type"},
    )
    assert r.status_code == 400


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
            location_type="neighborhood",
            formatted_address="Canon card only",
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
            formatted_address="Substrate geocode line",
            identity_fingerprint="fp-link-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
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
    assert r.json()["message"] == "linked"
    assert int(r.json()["stylebook_location_canonical_id"]) == cid

    with Session(engine) as s:
        row = s.get(SubstrateLocation, sid)
        assert row is not None
        assert int(row.stylebook_location_canonical_id or 0) == cid
        assert row.canonical_link_status == CANONICAL_LINK_LINKED
        assert row.canonical_review_reasons_json == [
            {"code": "linked_manual_accept_existing", "canonical_id": cid}
        ]
        aliases = s.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == cid,
            )
        ).all()
        assert len(aliases) == 1
        assert aliases[0].normalized_alias == "linkme"
        canon2 = s.get(StylebookLocationCanonical, cid)
        assert canon2 is not None
        assert canon2.location_type == "neighborhood"
        assert canon2.formatted_address == "Canon card only"


def test_accept_rejects_non_pending_candidate(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        loc = SubstrateLocation(
            project_id=pid,
            name="Stale",
            normalized_name="stale",
            location_type="city",
            identity_fingerprint="fp-stale-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_UNLINKED,
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]

    r = client.post(
        f"/v1/candidates/{sid}/accept?project_slug=demo-proj",
        headers=_service_headers(),
        json={"create_new": True, "name": "X"},
    )
    assert r.status_code == 400


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
    assert m0["substrate_location_id"] == lid
    assert m0["mention_id"] == mid
    assert m0["article_id"] == aid
    assert m0["article_headline"] == "Chicago story"
    assert m0["article_url"] == "https://example.com/chicago-story"
    assert m0["original_text"] == "Chicago skyline"
    assert m0["description"] == "setting"
    assert m0["mention_nature"] == "primary"


def test_post_unlink_canonical_prunes_alias_when_sole_substrate(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Sole Canon",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.commit()
        s.refresh(canon)
        cid = int(canon.id)  # type: ignore[arg-type]
        loc = SubstrateLocation(
            project_id=pid,
            name="Soleplace",
            normalized_name="soleplace",
            location_type="city",
            identity_fingerprint="fp-sole-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]

    r_link = client.post(
        f"/v1/locations/{sid}/link-canonical?project_slug=demo-proj",
        headers=_service_headers(),
        json={"stylebook_location_canonical_id": cid},
    )
    assert r_link.status_code == 200
    assert r_link.json()["changed"] is True

    with Session(engine) as s:
        aliases_before = s.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == cid,
                StylebookLocationAlias.normalized_alias == "soleplace",
            )
        ).all()
        assert len(aliases_before) >= 1

    r_un = client.post(
        f"/v1/locations/{sid}/unlink-canonical?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r_un.status_code == 200
    assert r_un.json() == {"message": "unlinked"}

    with Session(engine) as s:
        row = s.get(SubstrateLocation, sid)
        assert row is not None
        assert row.stylebook_location_canonical_id is None
        assert row.canonical_link_status == CANONICAL_LINK_PENDING
        aliases_after = s.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == cid,
                StylebookLocationAlias.normalized_alias == "soleplace",
            )
        ).all()
        assert len(aliases_after) == 0


def test_post_unlink_canonical_keeps_alias_when_second_substrate_shares_norm(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Shared Canon",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.commit()
        s.refresh(canon)
        cid = int(canon.id)  # type: ignore[arg-type]
        loc1 = SubstrateLocation(
            project_id=pid,
            name="Dup A",
            normalized_name="dupnorm",
            location_type="city",
            identity_fingerprint="fp-dup-a",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        loc2 = SubstrateLocation(
            project_id=pid,
            name="Dup B",
            normalized_name="dupnorm",
            location_type="city",
            identity_fingerprint="fp-dup-b",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        s.add(loc1)
        s.add(loc2)
        s.commit()
        s.refresh(loc1)
        s.refresh(loc2)
        sid1 = int(loc1.id)  # type: ignore[arg-type]
        sid2 = int(loc2.id)  # type: ignore[arg-type]

    assert (
        client.post(
            f"/v1/locations/{sid1}/link-canonical?project_slug=demo-proj",
            headers=_service_headers(),
            json={"stylebook_location_canonical_id": cid},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/v1/locations/{sid2}/link-canonical?project_slug=demo-proj",
            headers=_service_headers(),
            json={"stylebook_location_canonical_id": cid},
        ).status_code
        == 200
    )

    assert (
        client.post(
            f"/v1/locations/{sid1}/unlink-canonical?project_slug=demo-proj",
            headers=_service_headers(),
        ).status_code
        == 200
    )

    with Session(engine) as s:
        aliases = s.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == cid,
                StylebookLocationAlias.normalized_alias == "dupnorm",
            )
        ).all()
        assert len(aliases) >= 1


def test_post_link_canonical_relink_moves_alias_and_prunes_old_when_safe(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        ca = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Canon A",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        cb = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Canon B",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(ca)
        s.add(cb)
        s.commit()
        s.refresh(ca)
        s.refresh(cb)
        aid = int(ca.id)  # type: ignore[arg-type]
        bid = int(cb.id)  # type: ignore[arg-type]
        loc = SubstrateLocation(
            project_id=pid,
            name="Moveme",
            normalized_name="moveme",
            location_type="city",
            identity_fingerprint="fp-move-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]

    assert (
        client.post(
            f"/v1/locations/{sid}/link-canonical?project_slug=demo-proj",
            headers=_service_headers(),
            json={"stylebook_location_canonical_id": aid},
        ).json()["changed"]
        is True
    )
    r2 = client.post(
        f"/v1/locations/{sid}/link-canonical?project_slug=demo-proj",
        headers=_service_headers(),
        json={"stylebook_location_canonical_id": bid},
    )
    assert r2.status_code == 200
    assert r2.json()["changed"] is True

    with Session(engine) as s:
        row = s.get(SubstrateLocation, sid)
        assert row is not None
        assert int(row.stylebook_location_canonical_id or 0) == bid
        on_b = s.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == bid,
                StylebookLocationAlias.normalized_alias == "moveme",
            )
        ).all()
        assert len(on_b) >= 1
        on_a = s.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == aid,
                StylebookLocationAlias.normalized_alias == "moveme",
            )
        ).all()
        assert len(on_a) == 0


def test_post_link_canonical_idempotent_same_target(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Idem Canon",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.commit()
        s.refresh(canon)
        cid = int(canon.id)  # type: ignore[arg-type]
        loc = SubstrateLocation(
            project_id=pid,
            name="Idem",
            normalized_name="idem",
            location_type="city",
            identity_fingerprint="fp-idem-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]

    assert (
        client.post(
            f"/v1/locations/{sid}/link-canonical?project_slug=demo-proj",
            headers=_service_headers(),
            json={"stylebook_location_canonical_id": cid},
        ).json()["changed"]
        is True
    )
    r2 = client.post(
        f"/v1/locations/{sid}/link-canonical?project_slug=demo-proj",
        headers=_service_headers(),
        json={"stylebook_location_canonical_id": cid},
    )
    assert r2.status_code == 200
    assert r2.json()["changed"] is False


def test_get_canonical_linked_substrates(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="List Canon",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.commit()
        s.refresh(canon)
        cid = int(canon.id)  # type: ignore[arg-type]
        loc = SubstrateLocation(
            project_id=pid,
            name="Listed",
            normalized_name="listed",
            location_type="city",
            formatted_address="Listed City, ST, USA",
            identity_fingerprint="fp-list-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]

    assert (
        client.post(
            f"/v1/locations/{sid}/link-canonical?project_slug=demo-proj",
            headers=_service_headers(),
            json={"stylebook_location_canonical_id": cid},
        ).status_code
        == 200
    )

    r = client.get(
        f"/v1/canonical-locations/{cid}/linked-substrates?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["substrates"]) == 1
    assert data["substrates"][0]["id"] == sid
    assert data["substrates"][0]["normalized_name"] == "listed"
    assert data["substrates"][0]["formatted_address"] == "Listed City, ST, USA"


def test_get_suggested_canonicals_for_pending_candidate(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        loc = SubstrateLocation(
            project_id=pid,
            name="Suggestme",
            normalized_name="suggestme",
            location_type="city",
            identity_fingerprint="fp-sug-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]

    r = client.get(
        f"/v1/candidates/{sid}/suggested-canonicals?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    body = r.json()
    assert "suggestions" in body
    assert isinstance(body["suggestions"], list)
