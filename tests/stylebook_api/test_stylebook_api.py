"""Integration-style tests for Stylebook API (no Docker)."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldUser,
    BackfieldWorkspace,
    Stylebook,
    StylebookConnection,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    StylebookLocationMeta,
    StylebookMembership,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_entities.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_UNLINKED,
    CANONICAL_LINK_WAIVED,
)
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, select
from stylebook_api.deps import get_auth as get_auth_dep
from stylebook_api.deps import get_session
from stylebook_api.main import app


@pytest.fixture
def _stylebook_test_stack(
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


def _session_auth_for_user(user: BackfieldUser, *, org_id: int, org_role: str) -> dict[str, Any]:
    return {
        "type": "session",
        "user": user,
        "token_data": {},
        "organization_id": int(org_id),
        "org_role": str(org_role),
        "is_admin": bool(org_role == "org_admin"),
    }


@pytest.fixture
def member_client(
    _stylebook_test_stack: tuple[TestClient, Engine],
) -> Generator[TestClient, None, None]:
    """Client authenticated as a non-admin session user in org 1."""
    client, engine = _stylebook_test_stack
    with Session(engine) as s:
        user = BackfieldUser(email="member@example.com", password_hash="x")
        s.add(user)
        s.commit()

    def _get_auth_override() -> dict[str, Any]:
        with Session(engine) as s:
            u = s.exec(
                select(BackfieldUser).where(BackfieldUser.email == "member@example.com")
            ).one()
            return _session_auth_for_user(u, org_id=1, org_role="member")

    app.dependency_overrides[get_auth_dep] = _get_auth_override
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_auth_dep, None)


@pytest.fixture
def editor_client(
    _stylebook_test_stack: tuple[TestClient, Engine],
) -> Generator[TestClient, None, None]:
    """Client authenticated as an editor for stylebook `default` in org 1."""
    client, engine = _stylebook_test_stack
    with Session(engine) as s:
        user = BackfieldUser(email="editor@example.com", password_hash="x")
        s.add(user)
        s.commit()
        s.refresh(user)
        sb = s.exec(select(Stylebook).where(Stylebook.slug == "default")).one()
        s.add(
            StylebookMembership(
                stylebook_id=int(sb.id),  # type: ignore[arg-type]
                user_id=int(user.id),  # type: ignore[arg-type]
                role="editor",
            )
        )
        s.commit()

    def _get_auth_override() -> dict[str, Any]:
        with Session(engine) as s:
            u = s.exec(
                select(BackfieldUser).where(BackfieldUser.email == "editor@example.com")
            ).one()
            return _session_auth_for_user(u, org_id=1, org_role="member")

    app.dependency_overrides[get_auth_dep] = _get_auth_override
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_auth_dep, None)


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


def test_stylebook_permissions_endpoint_false_for_member(member_client: TestClient) -> None:
    r = member_client.get("/v1/stylebooks/default/permissions")
    assert r.status_code == 200
    assert r.json().get("can_edit") is False


def test_stylebook_permissions_endpoint_true_for_editor(editor_client: TestClient) -> None:
    r = editor_client.get("/v1/stylebooks/default/permissions")
    assert r.status_code == 200
    assert r.json().get("can_edit") is True


def test_stylebook_scoped_canonical_create_requires_editor(member_client: TestClient) -> None:
    r = member_client.post(
        "/v1/stylebooks/default/canonical-locations",
        json={"label": "Nope", "location_type": "city"},
    )
    assert r.status_code == 403


def test_stylebook_scoped_canonical_create_allows_editor(editor_client: TestClient) -> None:
    r = editor_client.post(
        "/v1/stylebooks/default/canonical-locations",
        json={"label": "Allowed", "location_type": "city"},
    )
    assert r.status_code == 200


def test_stylebook_canonical_locations_sort_recent(editor_client: TestClient) -> None:
    r = editor_client.get("/v1/stylebooks/default/canonical-locations?sort=recent&limit=5")
    assert r.status_code == 200
    body = r.json()
    assert "canonicals" in body
    assert body["total"] >= 0


def test_stylebook_canonical_locations_min_mentions(editor_client: TestClient) -> None:
    r = editor_client.get("/v1/stylebooks/default/canonical-locations?min_mentions=1")
    assert r.status_code == 200
    assert r.json().get("canonicals") == []


def test_stylebook_scoped_import_requires_editor(member_client: TestClient) -> None:
    r = member_client.post(
        "/v1/stylebooks/default/import/geojson/analyze",
        json={"geojson": {"type": "FeatureCollection", "features": []}},
    )
    assert r.status_code == 403


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
    r = client.get("/v1/stylebooks/default/canonical-locations")
    assert r.status_code == 401


def test_import_geojson_analyze_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/v1/import/geojson/analyze?project_slug=demo-proj",
        json={"geojson": {"type": "FeatureCollection", "features": []}},
    )
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


def test_import_geojson_analyze_returns_properties(client: TestClient) -> None:
    r = client.post(
        "/v1/import/geojson/analyze?project_slug=demo-proj",
        headers=_service_headers(),
        json={
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-87.62, 41.88]},
                        "properties": {"name": "A", "type": "city"},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-87.61, 41.89]},
                        "properties": {"formatted_address": "X", "name": "B"},
                    },
                ],
            }
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["feature_count"] == 2
    assert body["available_properties"] == ["formatted_address", "name", "type"]
    assert body["sample_feature"] is not None


def test_import_geojson_analyze_splits_geometrycollection(client: TestClient) -> None:
    r = client.post(
        "/v1/import/geojson/analyze?project_slug=demo-proj",
        headers=_service_headers(),
        json={
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "GeometryCollection",
                            "geometries": [
                                {"type": "Point", "coordinates": [-87.62, 41.88]},
                                {"type": "Point", "coordinates": [-87.61, 41.89]},
                            ],
                        },
                        "properties": {"name": "A", "type": "city"},
                    }
                ],
            }
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["feature_count"] == 2


def test_import_geojson_analyze_rejects_non_featurecollection(client: TestClient) -> None:
    r = client.post(
        "/v1/import/geojson/analyze?project_slug=demo-proj",
        headers=_service_headers(),
        json={"geojson": {"type": "Point", "coordinates": [0, 0]}},
    )
    assert r.status_code == 400


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        (
            "/v1/import/geojson/analyze?project_slug=demo-proj",
            {"geojson": {"type": "FeatureCollection", "features": [], "pad": "x" * 100}},
        ),
        (
            "/v1/import/geojson?project_slug=demo-proj",
            {
                "geojson": {
                    "type": "FeatureCollection",
                    "features": [],
                    "pad": "x" * 100,
                },
                "mappings": {"label_property": "name", "location_type_property": "type"},
            },
        ),
    ],
    ids=["analyze", "import"],
)
def test_import_geojson_rejects_over_25mb(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    payload: dict[str, Any],
) -> None:
    import stylebook_api.routers.imports as imports_router

    monkeypatch.setattr(imports_router, "MAX_IMPORT_BYTES", 10)
    # No Content-Length is sent by TestClient here, so the router will use the JSON-dumped
    # size as a best-effort fallback.
    r = client.post(path, headers=_service_headers(), json=payload)
    assert r.status_code == 413


def test_import_geojson_creates_canonicals_with_partial_failures(client: TestClient) -> None:
    r = client.post(
        "/v1/import/geojson?project_slug=demo-proj",
        headers=_service_headers(),
        json={
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-87.62, 41.88]},
                        "properties": {"name": "A", "type": "city"},
                    },
                    {
                        "type": "Feature",
                        "geometry": None,
                        "properties": {"name": "B", "type": "city"},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-87.61, 41.89]},
                        "properties": {"name": "C"},
                    },
                ],
            },
            "mappings": {
                "label_property": "name",
                "location_type_property": "type",
                "formatted_address_property": "formatted_address",
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_features"] == 3
    assert body["created_count"] == 1
    assert body["failed_count"] == 2
    assert len(body["created"]) == 1
    assert body["created"][0]["label"] == "A"
    assert len(body["failed"]) == 2


def test_import_geojson_splits_geometrycollection_on_import(client: TestClient) -> None:
    r = client.post(
        "/v1/import/geojson?project_slug=demo-proj",
        headers=_service_headers(),
        json={
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "GeometryCollection",
                            "geometries": [
                                {"type": "Point", "coordinates": [-87.62, 41.88]},
                                {"type": "Point", "coordinates": [-87.61, 41.89]},
                            ],
                        },
                        "properties": {"name": "A", "type": "city"},
                    }
                ],
            },
            "mappings": {"label_property": "name", "location_type_property": "type"},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_features"] == 2
    assert body["created_count"] == 2
    assert body["failed_count"] == 0


def test_import_geojson_with_meta_property_mappings(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    r = client.post(
        "/v1/import/geojson?project_slug=demo-proj",
        headers=_service_headers(),
        json={
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-87.62, 41.88]},
                        "properties": {"name": "Spot A", "type": "place", "ref": 99},
                    }
                ],
            },
            "mappings": {"label_property": "name", "location_type_property": "type"},
            "meta_property_mappings": [{"property_key": "ref", "meta_type": "import_ref"}],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created_count"] == 1
    cid = body["created"][0]["canonical_id"]
    with Session(stylebook_test_engine) as s:
        metas = s.exec(
            select(StylebookLocationMeta).where(
                StylebookLocationMeta.stylebook_location_canonical_id == cid
            )
        ).all()
        assert len(metas) == 1
        assert metas[0].meta_type == "import_ref"
        assert metas[0].data_json == {"ref": 99}


def test_import_geojson_meta_rejects_unknown_property_key(client: TestClient) -> None:
    r = client.post(
        "/v1/import/geojson?project_slug=demo-proj",
        headers=_service_headers(),
        json={
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-87.62, 41.88]},
                        "properties": {"name": "X", "type": "city"},
                    }
                ],
            },
            "mappings": {"label_property": "name", "location_type_property": "type"},
            "meta_property_mappings": [{"property_key": "not_a_key", "meta_type": "t"}],
        },
    )
    assert r.status_code == 400


def test_import_geojson_meta_rejects_blank_meta_type(client: TestClient) -> None:
    r = client.post(
        "/v1/import/geojson?project_slug=demo-proj",
        headers=_service_headers(),
        json={
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-87.62, 41.88]},
                        "properties": {"name": "X", "type": "city"},
                    }
                ],
            },
            "mappings": {"label_property": "name", "location_type_property": "type"},
            "meta_property_mappings": [{"property_key": "name", "meta_type": "   "}],
        },
    )
    assert r.status_code == 400


def test_import_geojson_meta_skips_empty_property_silently(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    r = client.post(
        "/v1/import/geojson?project_slug=demo-proj",
        headers=_service_headers(),
        json={
            "geojson": {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-87.62, 41.88]},
                        "properties": {"name": "A", "type": "city", "notes": ""},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [-87.61, 41.89]},
                        "properties": {"name": "B", "type": "city", "notes": "saved"},
                    },
                ],
            },
            "mappings": {"label_property": "name", "location_type_property": "type"},
            "meta_property_mappings": [{"property_key": "notes", "meta_type": "note"}],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["created_count"] == 2
    cids = [row["canonical_id"] for row in body["created"]]
    with Session(stylebook_test_engine) as s:
        metas = s.exec(select(StylebookLocationMeta)).all()
        assert len(metas) == 1
        assert metas[0].stylebook_location_canonical_id in cids
        assert metas[0].meta_type == "note"
        assert metas[0].data_json == {"notes": "saved"}


def test_create_location_creates_standalone_canonical_and_alias_no_substrate(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    with Session(stylebook_test_engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        q = select(SubstrateLocation).where(SubstrateLocation.project_id == pid)
        before = len(s.exec(q).all())

    r = editor_client.post(
        "/v1/stylebooks/default/canonical-locations",
        json={
            "label": "West Garfield Park, Chicago, IL",
            "location_type": "neighborhood",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["label"] == "West Garfield Park, Chicago, IL"
    assert body.get("location_type") == "neighborhood"
    cid = str(body["id"])
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
        norms = {str(a.normalized_alias) for a in aliases}
        # We store a conservative ordinal/punctuation-stripped variant for better recall.
        assert "west garfield park, chicago, il" in norms
        assert "west garfield park chicago il" in norms


def test_list_canonical_locations_type_filter(
    editor_client: TestClient) -> None:
    r_city = editor_client.post(
        "/v1/stylebooks/default/canonical-locations",
        json={"label": "Filter City Row", "location_type": "city"},
    )
    assert r_city.status_code == 200
    r_nb = editor_client.post(
        "/v1/stylebooks/default/canonical-locations",
        json={"label": "Filter Neighborhood Row", "location_type": "neighborhood"},
    )
    assert r_nb.status_code == 200
    r_list = editor_client.get(
        "/v1/stylebooks/default/canonical-locations?type_filter=city",
    )
    assert r_list.status_code == 200
    data = r_list.json()
    labels = {c["label"] for c in data["canonicals"]}
    assert "Filter City Row" in labels
    assert "Filter Neighborhood Row" not in labels
    for row in data["canonicals"]:
        if row["label"] == "Filter City Row":
            assert row.get("location_type") == "city"
    r_bad = editor_client.get(
        "/v1/stylebooks/default/canonical-locations?type_filter=not_a_real_type",
    )
    # Canonical types include custom values; unknown filters are treated as "no matches" rather
    # than a hard 400.
    assert r_bad.status_code == 200
    data_bad = r_bad.json()
    assert data_bad["canonicals"] == []


def test_list_canonical_locations_orders_by_label_case_insensitive(
    editor_client: TestClient) -> None:
    for label in ("Zebra", "alpha", "Mike"):
        r = editor_client.post(
            "/v1/stylebooks/default/canonical-locations",
                json={"label": label},
        )
        assert r.status_code == 200
    r = editor_client.get(
        "/v1/stylebooks/default/canonical-locations?limit=50",
    )
    assert r.status_code == 200
    labels = [c["label"] for c in r.json()["canonicals"]]
    assert labels == ["alpha", "Mike", "Zebra"]


def test_list_canonical_locations_search_prefers_exact_then_prefix_then_contains(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    _ = stylebook_test_engine
    from urllib.parse import quote

    # Contiguous substring filter: every row must contain the full query text.
    exact_query = "CanonSearchToken Chicago, IL"
    a = f"{exact_query} Extra Words"
    b = exact_query
    c = f"{exact_query} More"
    for lb in (a, b, c):
        r = editor_client.post(
            "/v1/stylebooks/default/canonical-locations",
                json={"label": lb},
        )
        assert r.status_code == 200

    q = quote(exact_query)
    r = editor_client.get(
        f"/v1/stylebooks/default/canonical-locations?q={q}&limit=200",
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
        r = editor_client.post(
            "/v1/stylebooks/default/canonical-locations",
                json={"label": lb},
        )
        assert r.status_code == 200

    q2 = quote(prefix_query)
    r2 = editor_client.get(
        f"/v1/stylebooks/default/canonical-locations?q={q2}&limit=200",
    )
    assert r2.status_code == 200
    labels2 = [row["label"] for row in r2.json()["canonicals"]]
    assert a2 in labels2 and b2 in labels2 and c2 in labels2
    assert labels2.index(b2) < labels2.index(a2)
    assert labels2.index(b2) < labels2.index(c2)


def test_list_canonical_locations_returns_catalog_not_substrate(
    editor_client: TestClient) -> None:
    r = editor_client.post(
        "/v1/stylebooks/default/canonical-locations",
        json={"label": "Catalog Test Place", "location_type": "city"},
    )
    assert r.status_code == 200
    created = r.json()
    canon_fk = str(created["id"])
    assert created["label"] == "Catalog Test Place"
    r2 = editor_client.get(
        "/v1/stylebooks/default/canonical-locations",
    )
    assert r2.status_code == 200
    data = r2.json()
    assert data["total"] >= 1
    canon = next(c for c in data["canonicals"] if c["label"] == "Catalog Test Place")
    assert str(canon["id"]) == str(canon_fk)
    assert canon.get("linked_substrate_count", 0) == 0
    r3 = editor_client.get(
        f"/v1/stylebooks/default/canonical-locations/{canon['id']}",
    )
    assert r3.status_code == 200
    assert r3.json()["label"] == "Catalog Test Place"


def test_patch_canonical_location_updates_location_type_and_formatted_address(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    _ = stylebook_test_engine
    r = editor_client.post(
        "/v1/stylebooks/default/canonical-locations",
        json={"label": "Patchable Canon Row"},
    )
    assert r.status_code == 200
    cid = str(r.json()["id"])
    r2 = editor_client.patch(
        f"/v1/stylebooks/default/canonical-locations/{cid}",
        json={"location_type": "city", "formatted_address": "Patchable, IL, USA"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["location_type"] == "city"
    assert body["formatted_address"] == "Patchable, IL, USA"
    r3 = editor_client.get(
        f"/v1/stylebooks/default/canonical-locations/{cid}",
    )
    assert r3.status_code == 200
    assert r3.json()["location_type"] == "city"
    assert r3.json()["formatted_address"] == "Patchable, IL, USA"
    r4 = editor_client.patch(
        f"/v1/stylebooks/default/canonical-locations/{cid}",
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
    engine = stylebook_test_engine
    with Session(engine) as s:
        user = BackfieldUser(email="stats-canon-writer@example.com", password_hash="x")
        s.add(user)
        s.commit()
        s.refresh(user)
        writer_id = int(user.id)  # type: ignore[arg-type]

    def _writer_auth() -> dict[str, Any]:
        with Session(engine) as s:
            u = s.get(BackfieldUser, writer_id)
            assert u is not None
            return _session_auth_for_user(u, org_id=1, org_role="org_admin")

    app.dependency_overrides[get_auth_dep] = _writer_auth
    try:
        r_loc = client.post(
            "/v1/stylebooks/default/canonical-locations",
            json={"label": "Stats Town", "location_type": "city"},
        )
        assert r_loc.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_dep, None)

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
    assert len(types) == 17


def test_candidates_ok_when_project_has_no_workspace(client: TestClient) -> None:
    r = client.get(
        "/v1/candidates?project_slug=no-ws-proj&status=open",
        headers=_service_headers(),
    )
    assert r.status_code == 200


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


def test_accept_deferred_candidate_create_new(
    client: TestClient, stylebook_test_engine: object
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        loc = SubstrateLocation(
            project_id=pid,
            name="Deferred Create",
            normalized_name="deferred create",
            location_type="city",
            identity_fingerprint="fp-deferred-create-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]

    r_def = client.post(
        f"/v1/candidates/{sid}/defer?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r_def.status_code == 200

    r_suggest = client.get(
        f"/v1/candidates/{sid}/suggested-canonicals?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r_suggest.status_code == 200

    r_accept = client.post(
        f"/v1/candidates/{sid}/accept?project_slug=demo-proj",
        headers=_service_headers(),
        json={"create_new": True, "name": "Deferred Create Canon"},
    )
    assert r_accept.status_code == 200
    cid = r_accept.json()["stylebook_location_canonical_id"]

    r_deferred = client.get(
        "/v1/candidates?project_slug=demo-proj&status=deferred",
        headers=_service_headers(),
    )
    assert r_deferred.status_code == 200
    assert r_deferred.json()["total"] == 0

    with Session(engine) as s:
        row = s.get(SubstrateLocation, sid)
        assert row is not None
        assert row.canonical_link_status == CANONICAL_LINK_LINKED
        assert row.stylebook_location_canonical_id == cid


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
    assert cand["canonical_review_lines"] == ["Private place or residence"]


def test_open_candidate_lists_canonical_review_lines(
    client: TestClient, stylebook_test_engine: object
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        loc = SubstrateLocation(
            project_id=pid,
            name="Greg Abbott",
            normalized_name="greg abbott",
            location_type="place",
            identity_fingerprint="fp-review-lines-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
            canonical_review_reasons_json=[
                {
                    "code": "ambiguous_canonical_match",
                    "recall_canonical_ids": ["id-1", "id-2"],
                },
                {
                    "code": "canonical_adjudication",
                    "rationale": "Not the same place as recalled entries.",
                    "outcome": "no_high_confidence_link",
                },
            ],
        )
        s.add(loc)
        s.commit()

    r = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open",
        headers=_service_headers(),
    )
    assert r.status_code == 200
    cand = r.json()["candidates"][0]
    assert cand["canonical_review_lines"] == [
        "Several Stylebook locations could match (2 recalled).",
        "Not the same place as recalled entries.",
    ]


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


def test_create_location_from_article_evidence(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        text = "Neighbors gathered at Lincoln School after the storm."
        art = SubstrateArticle(
            project_id=pid,
            headline="Storm response",
            text=text,
            url="https://example.com/add-place",
            deleted=False,
        )
        s.add(art)
        s.commit()
        s.refresh(art)
        aid = int(art.id)  # type: ignore[arg-type]

    start = text.index("Lincoln School")
    end = len(text)
    r = client.post(
        "/v1/locations/from-article-evidence?project_slug=demo-proj",
        headers=_service_headers(),
        json={
            "article_id": aid,
            "run_id": "run-123",
            "label": "Lincoln School",
            "location_type": "place",
            "mention_text": "Lincoln School",
            "quote_text": text[start:end],
            "start_char": start,
            "end_char": end,
            "role_in_story": "Shelter after the storm",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["anchor"].startswith("user_place:")
    loc_id = int(body["location"]["id"])
    assert body["location"]["name"] == "Lincoln School"
    assert body["location"]["location_type"] == "place"
    assert body["location"]["geometry_json"] is None

    with Session(engine) as s:
        loc = s.get(SubstrateLocation, loc_id)
        assert loc is not None
        assert loc.status == "active"
        assert loc.canonical_link_status == CANONICAL_LINK_PENDING
        assert loc.source_kind == "manual_add"
        assert loc.source_details_json["run_id"] == "run-123"
        assert loc.source_details_json["raw_entry_id"] == body["anchor"]
        mention = s.exec(
            select(SubstrateLocationMention).where(
                SubstrateLocationMention.location_id == loc_id,
                SubstrateLocationMention.article_id == aid,
            )
        ).one()
        assert mention.added is True
        assert mention.source_kind == "manual_add"
        assert mention.role_in_story == "Shelter after the storm"
        occurrence = s.exec(
            select(SubstrateLocationMentionOccurrence).where(
                SubstrateLocationMentionOccurrence.location_mention_id == int(mention.id)
            )
        ).one()
        assert occurrence.source_kind == "manual_add"
        assert occurrence.mention_text == "Lincoln School"
        assert occurrence.quote_text == text[start:end]
        assert occurrence.start_char == start
        assert occurrence.end_char == end


def test_create_person_from_article_evidence(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        text = "Mayor Jane Doe announced a new policy at city hall."
        art = SubstrateArticle(
            project_id=pid,
            headline="Policy announcement",
            text=text,
            url="https://example.com/add-person",
            deleted=False,
        )
        s.add(art)
        s.commit()
        s.refresh(art)
        aid = int(art.id)  # type: ignore[arg-type]

    start = text.index("Mayor Jane Doe")
    end = start + len("Mayor Jane Doe")
    r = client.post(
        "/v1/people/from-article-evidence?project_slug=demo-proj",
        headers=_service_headers(),
        json={
            "article_id": aid,
            "run_id": "run-456",
            "name": "Jane Doe",
            "person_type": "politician",
            "title": "Mayor",
            "affiliation": "City of Example",
            "nature": "official",
            "mention_text": "Mayor Jane Doe",
            "quote_text": text[start:end],
            "start_char": start,
            "end_char": end,
            "role_in_story": "Announced policy",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["anchor"].startswith("user_person:")
    person_id = int(body["person"]["id"])
    assert body["person"]["name"] == "Jane Doe"
    assert body["person"]["person_type"] == "elected_official"
    assert body["person"]["canonical_link_status"] == CANONICAL_LINK_PENDING

    with Session(engine) as s:
        person = s.get(SubstratePerson, person_id)
        assert person is not None
        assert person.status == "active"
        assert person.source_kind == "manual_add"
        assert person.source_details_json["run_id"] == "run-456"
        assert person.source_details_json["raw_entry_id"] == body["anchor"]
        mention = s.exec(
            select(SubstratePersonMention).where(
                SubstratePersonMention.person_id == person_id,
                SubstratePersonMention.article_id == aid,
            )
        ).one()
        assert mention.added is True
        assert mention.source_kind == "manual_add"
        assert mention.nature == "official"
        assert mention.role_in_story == "Announced policy"
        occurrence = s.exec(
            select(SubstratePersonMentionOccurrence).where(
                SubstratePersonMentionOccurrence.person_mention_id == int(mention.id)
            )
        ).one()
        assert occurrence.source_kind == "manual_add"
        assert occurrence.mention_text == "Mayor Jane Doe"
        assert occurrence.quote_text == text[start:end]
        assert occurrence.start_char == start
        assert occurrence.end_char == end


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
        canon = s.get(StylebookLocationCanonical, str(row.stylebook_location_canonical_id))
        assert canon is not None
        coid = str(canon.id)
        assert data["stylebook_location_canonical_id"] == coid
        assert row.canonical_review_reasons_json == [
            {"code": "linked_manual_accept_create_new", "canonical_id": coid}
        ]
        assert canon.label == "Newplace Canon"
        assert canon.location_type == "city"
        assert canon.formatted_address == "Newplace, IL, USA"
        assert canon.primary_substrate_location_id is None
        canon_id = str(canon.id)
        aliases = s.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == canon_id,
            )
        ).all()
        assert len(aliases) == 1
        assert aliases[0].normalized_alias == "newplace"


def test_accept_candidate_create_new_inherits_substrate_geometry(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    """Accept create_new copies substrate geometry when the client omits geometry_json."""
    engine = stylebook_test_engine
    gj: dict = {"type": "Point", "coordinates": [-87.6298, 41.8781]}
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        loc = SubstrateLocation(
            project_id=pid,
            name="GeomPlace",
            normalized_name="geomplace",
            location_type="address",
            formatted_address="GeomPlace, Chicago, IL",
            identity_fingerprint="fp-geom-inherit-1",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
            geometry_json=gj,
            geometry_type="Point",
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]

    r = client.post(
        f"/v1/candidates/{sid}/accept?project_slug=demo-proj",
        headers=_service_headers(),
        json={"create_new": True, "name": "Geom Canon"},
    )
    assert r.status_code == 200

    with Session(engine) as s:
        row = s.get(SubstrateLocation, sid)
        assert row is not None
        canon = s.get(StylebookLocationCanonical, str(row.stylebook_location_canonical_id))
        assert canon is not None
        assert canon.geometry_json == gj
        assert canon.geometry_type == "Point"


def test_patch_saved_place_geometry_clear_with_null(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    """``PATCH …/locations/{id}/geometry`` accepts explicit ``geometry_json: null`` to clear."""
    engine = stylebook_test_engine
    gj: dict = {"type": "Point", "coordinates": [-87.6298, 41.8781]}
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        loc = SubstrateLocation(
            project_id=pid,
            name="ClearGeom",
            normalized_name="cleargeom",
            location_type="address",
            geometry_json=gj,
            geometry_type="Point",
        )
        s.add(loc)
        s.commit()
        s.refresh(loc)
        sid = int(loc.id)  # type: ignore[arg-type]

    r = client.patch(
        f"/v1/locations/{sid}/geometry?project_slug=demo-proj",
        headers=_service_headers(),
        json={"geometry_json": None},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["geometry_json"] is None
    assert body["geometry_type"] is None

    with Session(engine) as s:
        row = s.get(SubstrateLocation, sid)
        assert row is not None
        assert row.geometry_json is None
        assert row.geometry_type is None


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
        canon = s.get(StylebookLocationCanonical, str(row.stylebook_location_canonical_id))
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
            slug="existing",
            location_type="neighborhood",
            formatted_address="Canon card only",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.commit()
        s.refresh(canon)
        cid = str(canon.id)

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
    assert r.json()["stylebook_location_canonical_id"] == cid

    with Session(engine) as s:
        row = s.get(SubstrateLocation, sid)
        assert row is not None
        assert row.stylebook_location_canonical_id == cid
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
    assert data["canonical_location_id"] == str(lid)
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
            slug="sole-canon",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.commit()
        s.refresh(canon)
        cid = str(canon.id)
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


def test_delete_location_article_scoped_removes_orphan_linked_substrate_without_requeue(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    """Sole mention removed: unlink from canonical and delete row; not open candidates."""
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Austin",
            slug="austin-neighborhood",
            location_type="neighborhood",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.flush()
        cid = str(canon.id)
        art = SubstrateArticle(
            project_id=pid,
            headline="Gas prices",
            text="Austin resident Malik Allen was gassing up.",
            url="https://example.com/gas",
            deleted=False,
        )
        s.add(art)
        s.flush()
        aid = int(art.id)  # type: ignore[arg-type]
        loc = SubstrateLocation(
            project_id=pid,
            name="5400 W West End Ave",
            normalized_name="5400 w west end ave",
            location_type="address",
            identity_fingerprint="fp-west-end-gas",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        s.add(loc)
        s.flush()
        sid = int(loc.id)  # type: ignore[arg-type]
        s.add(
            SubstrateLocationMention(
                article_id=aid,
                location_id=sid,
                needs_review=False,
                deleted=False,
            )
        )
        s.commit()

    r_link = client.post(
        f"/v1/locations/{sid}/link-canonical?project_slug=demo-proj",
        headers=_service_headers(),
        json={"stylebook_location_canonical_id": cid},
    )
    assert r_link.status_code == 200

    r_del = client.delete(
        f"/v1/locations/{sid}?project_slug=demo-proj&article_id={aid}",
        headers=_service_headers(),
    )
    assert r_del.status_code == 200
    body = r_del.json()
    assert body["mentions_removed"] == 1
    assert body["location_deleted"] is True
    assert body["candidates_created"] == 0

    with Session(engine) as s:
        assert s.get(SubstrateLocation, sid) is None
        men = s.exec(
            select(SubstrateLocationMention).where(
                SubstrateLocationMention.location_id == sid,
                SubstrateLocationMention.article_id == aid,
            )
        ).one()
        assert men.deleted is True

    r_cand = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open&q=west+end",
        headers=_service_headers(),
    )
    assert r_cand.status_code == 200
    assert not any(c["id"] == sid for c in r_cand.json()["candidates"])


def test_delete_location_article_scoped_keeps_link_when_other_stories_mention(
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
            label="Shared place",
            slug="shared-place",
            location_type="place",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.flush()
        cid = str(canon.id)
        art_a = SubstrateArticle(
            project_id=pid,
            headline="Story A",
            text="First story.",
            url="https://example.com/a",
            deleted=False,
        )
        art_b = SubstrateArticle(
            project_id=pid,
            headline="Story B",
            text="Second story.",
            url="https://example.com/b",
            deleted=False,
        )
        s.add(art_a)
        s.add(art_b)
        s.flush()
        aid_a = int(art_a.id)  # type: ignore[arg-type]
        aid_b = int(art_b.id)  # type: ignore[arg-type]
        loc = SubstrateLocation(
            project_id=pid,
            name="Shared Ave",
            normalized_name="shared ave",
            location_type="address",
            identity_fingerprint="fp-shared",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        s.add(loc)
        s.flush()
        sid = int(loc.id)  # type: ignore[arg-type]
        s.add(
            SubstrateLocationMention(
                article_id=aid_a,
                location_id=sid,
                needs_review=False,
                deleted=False,
            )
        )
        s.add(
            SubstrateLocationMention(
                article_id=aid_b,
                location_id=sid,
                needs_review=False,
                deleted=False,
            )
        )
        s.commit()

    r_link = client.post(
        f"/v1/locations/{sid}/link-canonical?project_slug=demo-proj",
        headers=_service_headers(),
        json={"stylebook_location_canonical_id": cid},
    )
    assert r_link.status_code == 200

    r_del = client.delete(
        f"/v1/locations/{sid}?project_slug=demo-proj&article_id={aid_a}",
        headers=_service_headers(),
    )
    assert r_del.status_code == 200
    body = r_del.json()
    assert body["mentions_removed"] == 1
    assert body["location_deleted"] is False
    assert body["candidates_created"] == 0

    with Session(engine) as s:
        row = s.get(SubstrateLocation, sid)
        assert row is not None
        assert row.stylebook_location_canonical_id == cid
        assert row.canonical_link_status == CANONICAL_LINK_LINKED
        active = s.exec(
            select(SubstrateLocationMention).where(
                SubstrateLocationMention.location_id == sid,
                SubstrateLocationMention.deleted == False,  # noqa: E712
            )
        ).all()
        assert len(active) == 1
        assert int(active[0].article_id) == aid_b


def test_delete_location_article_scoped_unlinks_when_canonical_in_non_default_stylebook(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    """Delete must unlink using the canonical's stylebook, not only the project default."""
    engine = stylebook_test_engine
    with Session(engine) as s:
        org = s.exec(
            select(BackfieldOrganization).where(BackfieldOrganization.slug == "default")
        ).one()
        oid = int(org.id)
        default_sb = s.exec(
            select(Stylebook).where(
                Stylebook.organization_id == oid,
                Stylebook.is_default.is_(True),
            )
        ).one()
        other_sb = Stylebook(
            organization_id=oid,
            slug="regional",
            name="Regional Stylebook",
            is_default=False,
        )
        s.add(other_sb)
        s.flush()
        other_sb_id = int(other_sb.id)
        assert int(default_sb.id) != other_sb_id

        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        canon = StylebookLocationCanonical(
            stylebook_id=other_sb_id,
            label="South Shore",
            slug="south-shore-regional",
            location_type="neighborhood",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.flush()
        cid = str(canon.id)
        art = SubstrateArticle(
            project_id=pid,
            headline="Story",
            text="In South Shore.",
            url="https://example.com/ss",
            deleted=False,
        )
        s.add(art)
        s.flush()
        aid = int(art.id)  # type: ignore[arg-type]
        loc = SubstrateLocation(
            project_id=pid,
            name="South Shore",
            normalized_name="south shore",
            location_type="neighborhood",
            identity_fingerprint="fp-south-shore",
            stylebook_location_canonical_id=cid,
            canonical_link_status=CANONICAL_LINK_LINKED,
        )
        s.add(loc)
        s.flush()
        sid = int(loc.id)  # type: ignore[arg-type]
        s.add(
            SubstrateLocationMention(
                article_id=aid,
                location_id=sid,
                needs_review=False,
                deleted=False,
            )
        )
        s.commit()

    r_del = client.delete(
        f"/v1/locations/{sid}?project_slug=demo-proj"
        f"&article_id={aid}&stylebook_slug=regional",
        headers=_service_headers(),
    )
    assert r_del.status_code == 200, r_del.text
    assert r_del.json()["location_deleted"] is True
    assert r_del.json()["candidates_created"] == 0

    with Session(engine) as s:
        assert s.get(SubstrateLocation, sid) is None


def test_delete_location_without_article_id_requeues_linked_substrate(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    """Agate review may omit article_id; linked rows must not be hard-deleted."""
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        ws = s.get(BackfieldWorkspace, int(proj.workspace_id))  # type: ignore[arg-type]
        sb_id = int(ws.stylebook_id)
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Loop",
            slug="loop-place",
            location_type="place",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.flush()
        cid = str(canon.id)
        art = SubstrateArticle(
            project_id=pid,
            headline="Loop story",
            text="Near the Loop.",
            url="https://example.com/loop",
            deleted=False,
        )
        s.add(art)
        s.flush()
        aid = int(art.id)  # type: ignore[arg-type]
        loc = SubstrateLocation(
            project_id=pid,
            name="Chicago Loop",
            normalized_name="chicago loop",
            location_type="neighborhood",
            identity_fingerprint="fp-loop",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        s.add(loc)
        s.flush()
        sid = int(loc.id)  # type: ignore[arg-type]
        s.add(
            SubstrateLocationMention(
                article_id=aid,
                location_id=sid,
                needs_review=False,
                deleted=False,
            )
        )
        s.commit()

    r_link = client.post(
        f"/v1/locations/{sid}/link-canonical?project_slug=demo-proj",
        headers=_service_headers(),
        json={"stylebook_location_canonical_id": cid},
    )
    assert r_link.status_code == 200

    r_del = client.delete(
        f"/v1/locations/{sid}?project_slug=demo-proj",
        headers=_service_headers(),
    )
    assert r_del.status_code == 200
    body = r_del.json()
    assert body["mentions_removed"] == 1
    assert body["location_deleted"] is False
    assert body["candidates_created"] == 1

    with Session(engine) as s:
        row = s.get(SubstrateLocation, sid)
        assert row is not None
        assert row.stylebook_location_canonical_id is None
        assert row.canonical_link_status == CANONICAL_LINK_PENDING

    r_cand = client.get(
        "/v1/candidates?project_slug=demo-proj&status=open&q=loop",
        headers=_service_headers(),
    )
    assert r_cand.status_code == 200
    assert any(c["id"] == sid for c in r_cand.json()["candidates"])


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
            slug="shared-canon",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.commit()
        s.refresh(canon)
        cid = str(canon.id)
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
            slug="canon-a",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        cb = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Canon B",
            slug="canon-b",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(ca)
        s.add(cb)
        s.commit()
        s.refresh(ca)
        s.refresh(cb)
        aid = str(ca.id)
        bid = str(cb.id)
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
        assert row.stylebook_location_canonical_id == bid
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
            slug="idem-canon",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.commit()
        s.refresh(canon)
        cid = str(canon.id)
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
            slug="list-canon",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.commit()
        s.refresh(canon)
        cid = str(canon.id)
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

    with Session(engine) as s:
        user = BackfieldUser(email="linked-substrates-reader@example.com", password_hash="x")
        s.add(user)
        s.commit()
        s.refresh(user)
        reader_id = int(user.id)  # type: ignore[arg-type]

    def _reader_auth() -> dict[str, Any]:
        with Session(engine) as s:
            u = s.get(BackfieldUser, reader_id)
            assert u is not None
            return _session_auth_for_user(u, org_id=1, org_role="org_admin")

    app.dependency_overrides[get_auth_dep] = _reader_auth
    try:
        r = client.get(
            f"/v1/stylebooks/default/canonical-locations/{cid}/linked-substrates",
        )
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_auth_dep, None)
    data = r.json()
    assert len(data["substrates"]) == 1
    assert data["substrates"][0]["id"] == sid
    assert data["substrates"][0]["normalized_name"] == "listed"
    assert data["substrates"][0]["formatted_address"] == "Listed City, ST, USA"


def test_stylebook_canonical_linked_substrates_include_project_fields(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        user = BackfieldUser(email="stylebook-admin@example.com", password_hash="x")
        s.add(user)
        s.commit()
        s.refresh(user)
        demo_proj = s.exec(
            select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")
        ).one()
        other_proj = s.exec(
            select(BackfieldProject).where(BackfieldProject.slug == "no-ws-proj")
        ).one()
        ws = s.get(BackfieldWorkspace, int(demo_proj.workspace_id))  # type: ignore[arg-type]
        assert ws is not None
        sb_id = int(ws.stylebook_id)
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Shared Canon",
            slug="shared-canon",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.commit()
        s.refresh(canon)
        cid = str(canon.id)
        loc_a = SubstrateLocation(
            project_id=int(demo_proj.id),  # type: ignore[arg-type]
            name="Alpha",
            normalized_name="alpha",
            location_type="city",
            identity_fingerprint="fp-alpha",
            stylebook_location_canonical_id=cid,
            canonical_link_status=CANONICAL_LINK_LINKED,
        )
        loc_b = SubstrateLocation(
            project_id=int(other_proj.id),  # type: ignore[arg-type]
            name="Beta",
            normalized_name="beta",
            location_type="city",
            identity_fingerprint="fp-beta",
            stylebook_location_canonical_id=cid,
            canonical_link_status=CANONICAL_LINK_LINKED,
        )
        s.add(loc_a)
        s.add(loc_b)
        s.commit()
        s.refresh(loc_a)
        s.refresh(loc_b)
        loc_a_id = int(loc_a.id)  # type: ignore[arg-type]
        demo_proj_id = int(demo_proj.id)  # type: ignore[arg-type]
        other_proj_id = int(other_proj.id)  # type: ignore[arg-type]
        admin_user_id = int(user.id)  # type: ignore[arg-type]

    def _get_auth_override() -> dict[str, Any]:
        with Session(engine) as s:
            u = s.get(BackfieldUser, admin_user_id)
            assert u is not None
            return _session_auth_for_user(u, org_id=1, org_role="org_admin")

    app.dependency_overrides[get_auth_dep] = _get_auth_override
    try:
        r_all = client.get(
            f"/v1/stylebooks/default/canonical-locations/{cid}/linked-substrates"
        )
        assert r_all.status_code == 200
        all_rows = r_all.json()["substrates"]
        assert [row["project_slug"] for row in all_rows] == ["demo-proj", "no-ws-proj"]
        assert [row["project_name"] for row in all_rows] == ["Demo", "No workspace"]
        assert [row["project_id"] for row in all_rows] == [demo_proj_id, other_proj_id]

        r_filtered = client.get(
            f"/v1/stylebooks/default/canonical-locations/{cid}/linked-substrates"
            "?project=demo-proj"
        )
        assert r_filtered.status_code == 200
        filtered_rows = r_filtered.json()["substrates"]
        assert len(filtered_rows) == 1
        assert filtered_rows[0]["id"] == loc_a_id
        assert filtered_rows[0]["project_slug"] == "demo-proj"
    finally:
        app.dependency_overrides.pop(get_auth_dep, None)


def test_get_suggested_canonicals_for_pending_candidate(
    client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        pid = int(proj.id)
        stylebook = s.exec(select(Stylebook).where(Stylebook.slug == "default")).one()
        canon = StylebookLocationCanonical(
            stylebook_id=int(stylebook.id),  # type: ignore[arg-type]
            label="Suggestme",
            slug="suggestme-canon",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.flush()
        s.add(
            StylebookLocationAlias(
                location_canonical_id=str(canon.id),
                alias_text="Suggestme",
                normalized_alias="suggestme",
                provenance="test",
                suppressed=False,
            )
        )
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
    assert len(body["suggestions"]) >= 1


def test_stylebook_canonical_location_meta_crud(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        stylebook = s.exec(select(Stylebook).where(Stylebook.slug == "default")).one()
        canon = StylebookLocationCanonical(
            stylebook_id=int(stylebook.id),  # type: ignore[arg-type]
            label="Shared Meta Canon",
            slug="shared-meta-canon",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(canon)
        s.commit()
        s.refresh(canon)
        cid = str(canon.id)

    r0 = editor_client.get(f"/v1/stylebooks/default/canonical-locations/{cid}/meta")
    assert r0.status_code == 200
    assert r0.json()["count"] == 0

    r1 = editor_client.post(
        f"/v1/stylebooks/default/canonical-locations/{cid}/meta",
        json={"meta_type": "tag", "data": {"shared": True}},
    )
    assert r1.status_code == 200
    mid = int(r1.json()["id"])

    r2 = editor_client.get(f"/v1/stylebooks/default/canonical-locations/{cid}/meta")
    assert r2.status_code == 200
    assert r2.json()["count"] == 1
    assert r2.json()["meta"][0]["data"] == {"shared": True}

    r3 = editor_client.patch(
        f"/v1/stylebooks/default/canonical-locations/{cid}/meta/{mid}",
        json={"data": {"shared": "everywhere"}, "meta_type": "note"},
    )
    assert r3.status_code == 200
    assert r3.json()["meta_type"] == "note"
    assert r3.json()["data"] == {"shared": "everywhere"}

    r4 = editor_client.delete(
        f"/v1/stylebooks/default/canonical-locations/{cid}/meta/{mid}"
    )
    assert r4.status_code == 200

    with Session(engine) as s:
        row = s.exec(
            select(StylebookLocationMeta).where(StylebookLocationMeta.id == mid)
        ).first()
        assert row is None


def test_stylebook_canonical_location_connections_roundtrip(
    editor_client: TestClient, stylebook_test_engine: Engine
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        stylebook = s.exec(select(Stylebook).where(Stylebook.slug == "default")).one()
        ca = StylebookLocationCanonical(
            stylebook_id=int(stylebook.id),  # type: ignore[arg-type]
            label="Shared Conn A",
            slug="shared-conn-a",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        cb = StylebookLocationCanonical(
            stylebook_id=int(stylebook.id),  # type: ignore[arg-type]
            label="Shared Conn B",
            slug="shared-conn-b",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(ca)
        s.add(cb)
        s.commit()
        s.refresh(ca)
        s.refresh(cb)
        aid = str(ca.id)
        bid = str(cb.id)

    r0 = editor_client.get(
        f"/v1/stylebooks/default/canonical-locations/{aid}/connections"
    )
    assert r0.status_code == 200
    assert r0.json()["connections"] == []

    r1 = editor_client.post(
        f"/v1/stylebooks/default/canonical-locations/{aid}/connections",
        json={"to_entity_type": "location", "to_entity_id": bid, "nature": "near"},
    )
    assert r1.status_code == 200
    body = r1.json()
    conn_id = int(body["id"])
    assert body["nature"] == "near"
    assert body.get("evidence_json") is None

    r2 = editor_client.get(
        f"/v1/stylebooks/default/canonical-locations/{aid}/connections"
    )
    assert r2.status_code == 200
    assert len(r2.json()["connections"]) == 1
    assert r2.json()["connections"][0]["to_display_name"] == "Shared Conn B"

    r2b = editor_client.get("/v1/connections/stylebooks/default/natures")
    assert r2b.status_code == 200
    assert "near" in r2b.json()["natures"]

    r3 = editor_client.patch(
        f"/v1/stylebooks/default/canonical-locations/{aid}/connections/{conn_id}",
        json={"nature": "adjacent"},
    )
    assert r3.status_code == 200
    assert r3.json()["nature"] == "adjacent"

    r4 = editor_client.delete(
        f"/v1/stylebooks/default/canonical-locations/{aid}/connections/{conn_id}"
    )
    assert r4.status_code == 200

    with Session(engine) as s:
        row = s.get(StylebookConnection, conn_id)
        assert row is None


def test_stylebook_person_and_organization_connections_list(
    editor_client: TestClient,
    stylebook_test_engine: Engine,
) -> None:
    """Auto-created person↔organization edges must list from both canonical detail pages."""
    engine = stylebook_test_engine
    with Session(engine) as s:
        stylebook = s.exec(select(Stylebook).where(Stylebook.slug == "default")).one()
        sb_id = int(stylebook.id)  # type: ignore[arg-type]
        person = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Conn Person",
            slug="conn-person",
            status="active",
        )
        organization = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Conn Org",
            slug="conn-org",
            organization_type="government",
            status="active",
        )
        s.add(person)
        s.add(organization)
        s.commit()
        s.refresh(person)
        s.refresh(organization)
        person_id = str(person.id)
        org_id = str(organization.id)
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        s.add(
            StylebookConnection(
                project_id=int(proj.id),
                from_entity_type="person",
                from_entity_id=person_id,
                to_entity_type="organization",
                to_entity_id=org_id,
                nature="works_for",
                evidence_json={
                    "source": "dboutput_auto_connections",
                    "confidence": 0.95,
                    "quote": "Jane works for Conn Org.",
                    "reason": "Explicit employment in text.",
                },
            )
        )
        s.commit()

    person_res = editor_client.get(
        f"/v1/stylebooks/default/canonical-people/{person_id}/connections"
    )
    assert person_res.status_code == 200
    person_rows = person_res.json()["connections"]
    assert len(person_rows) == 1
    assert person_rows[0]["nature"] == "works_for"
    assert person_rows[0]["to_display_name"] == "Conn Org"
    assert person_rows[0]["evidence_json"]["quote"] == "Jane works for Conn Org."

    org_res = editor_client.get(
        f"/v1/stylebooks/default/canonical-organizations/{org_id}/connections"
    )
    assert org_res.status_code == 200
    org_rows = org_res.json()["connections"]
    assert len(org_rows) == 1
    assert org_rows[0]["from_display_name"] == "Conn Person"


def test_stylebook_person_connection_crud(
    editor_client: TestClient,
    stylebook_test_engine: Engine,
) -> None:
    """Manual person connections can be created, updated, and deleted from stylebook routes."""
    engine = stylebook_test_engine
    with Session(engine) as s:
        stylebook = s.exec(select(Stylebook).where(Stylebook.slug == "default")).one()
        sb_id = int(stylebook.id)  # type: ignore[arg-type]
        person = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Manual Conn Person",
            slug="manual-conn-person",
            status="active",
        )
        location = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Manual Conn Place",
            slug="manual-conn-place",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(person)
        s.add(location)
        s.commit()
        s.refresh(person)
        s.refresh(location)
        person_id = str(person.id)
        location_id = str(location.id)

    create_res = editor_client.post(
        f"/v1/stylebooks/default/canonical-people/{person_id}/connections",
        json={
            "to_entity_type": "location",
            "to_entity_id": location_id,
            "nature": "born in",
        },
    )
    assert create_res.status_code == 200
    body = create_res.json()
    conn_id = int(body["id"])
    assert body["nature"] == "born in"
    assert body["to_display_name"] == "Manual Conn Place"
    assert body.get("evidence_json") is None

    list_res = editor_client.get(
        f"/v1/stylebooks/default/canonical-people/{person_id}/connections"
    )
    assert list_res.status_code == 200
    assert len(list_res.json()["connections"]) == 1

    update_res = editor_client.patch(
        f"/v1/stylebooks/default/canonical-people/{person_id}/connections/{conn_id}",
        json={"nature": "lives in"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["nature"] == "lives in"

    delete_res = editor_client.delete(
        f"/v1/stylebooks/default/canonical-people/{person_id}/connections/{conn_id}"
    )
    assert delete_res.status_code == 200

    with Session(engine) as s:
        row = s.get(StylebookConnection, conn_id)
        assert row is None


def test_stylebook_connection_lists_auto_connection_evidence(
    editor_client: TestClient,
    stylebook_test_engine: Engine,
) -> None:
    engine = stylebook_test_engine
    with Session(engine) as s:
        stylebook = s.exec(select(Stylebook).where(Stylebook.slug == "default")).one()
        ca = StylebookLocationCanonical(
            stylebook_id=int(stylebook.id),  # type: ignore[arg-type]
            label="Evidence Conn A",
            slug="evidence-conn-a",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        cb = StylebookLocationCanonical(
            stylebook_id=int(stylebook.id),  # type: ignore[arg-type]
            label="Evidence Conn B",
            slug="evidence-conn-b",
            location_type="city",
            primary_substrate_location_id=None,
            status="active",
        )
        s.add(ca)
        s.add(cb)
        s.commit()
        s.refresh(ca)
        s.refresh(cb)
        aid = str(ca.id)
        bid = str(cb.id)

    evidence = {
        "source": "dboutput_auto_connections",
        "confidence": 0.94,
        "quote": "Acme operates in Chicago.",
        "reason": "The story states where the organization operates.",
        "from_display_name": "Evidence Conn A",
        "to_display_name": "Evidence Conn B",
        "from_entity_type": "location",
        "from_entity_id": aid,
        "to_entity_type": "location",
        "to_entity_id": bid,
    }
    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        s.add(
            StylebookConnection(
                project_id=int(proj.id),
                from_entity_type="location",
                from_entity_id=aid,
                to_entity_type="location",
                to_entity_id=bid,
                nature="near",
                evidence_json=evidence,
            )
        )
        s.commit()

    response = editor_client.get(
        f"/v1/stylebooks/default/canonical-locations/{aid}/connections"
    )
    assert response.status_code == 200
    rows = response.json()["connections"]
    assert len(rows) == 1
    assert rows[0]["evidence_json"]["quote"] == "Acme operates in Chicago."
    assert rows[0]["evidence_json"]["confidence"] == 0.94


def test_stylebook_connection_exact_edge_unique_constraint(
    stylebook_test_engine: Engine,
) -> None:
    engine = stylebook_test_engine
    from sqlalchemy.exc import IntegrityError

    with Session(engine) as s:
        proj = s.exec(select(BackfieldProject).where(BackfieldProject.slug == "demo-proj")).one()
        first = StylebookConnection(
            project_id=int(proj.id),
            from_entity_type="location",
            from_entity_id="loc-a",
            to_entity_type="person",
            to_entity_id="person-a",
            nature="custom_edge",
        )
        duplicate = StylebookConnection(
            project_id=int(proj.id),
            from_entity_type="location",
            from_entity_id="loc-a",
            to_entity_type="person",
            to_entity_id="person-a",
            nature="custom_edge",
        )
        s.add(first)
        s.commit()
        s.add(duplicate)
        with pytest.raises(IntegrityError):
            s.commit()
        s.rollback()
