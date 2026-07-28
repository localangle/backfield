"""Tests for substrate cache fingerprint parity and :func:`try_resolve_geocode_cache`."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    SubstrateLocationCache,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.ingest.geocode_cache.fingerprint import (
    normalize_substrate_cache_query,
    substrate_location_cache_query_fingerprint,
)
from backfield_entities.ingest.geocode_cache.resolve import (
    build_geocode_cache_adjudication_candidates,
    materialize_canonical_match_dict,
    resolve_geocode_cache_strict_with_outcome,
    try_resolve_geocode_cache,
)
from sqlmodel import Session, SQLModel, create_engine


def test_fingerprint_stable_payload() -> None:
    a = substrate_location_cache_query_fingerprint(
        project_id=7,
        normalized_query="chicago, il",
        location_type="city",
    )
    b = substrate_location_cache_query_fingerprint(
        project_id=7,
        normalized_query="chicago, il",
        location_type="city",
    )
    assert a == b
    assert len(a) == 64


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_org_sb_project(session: Session) -> tuple[int, int, int]:
    org = BackfieldOrganization(name="O", slug="o-gcc")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = ensure_default_stylebook_for_organization(session, oid)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    ws = BackfieldWorkspace(
        organization_id=oid,
        stylebook_id=sb_id,
        name="W",
        slug="w-gcc",
    )
    session.add(ws)
    session.commit()
    session.refresh(ws)
    proj = BackfieldProject(
        organization_id=oid,
        name="P",
        slug="p-gcc",
        workspace_id=int(ws.id),  # type: ignore[arg-type]
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    pid = int(proj.id)  # type: ignore[arg-type]
    return pid, sb_id, oid


def test_try_resolve_single_canonical_winner() -> None:
    gj = {"type": "Point", "coordinates": [-87.0, 41.0]}
    engine = _engine()
    with Session(engine) as session:
        pid, sb_id, _ = _seed_org_sb_project(session)
        c = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            status="active",
            geometry_json=gj,
            geometry_type="Point",
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        cid = str(c.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="Chicago, IL",
                normalized_alias="chicago, il",
                provenance="test",
                suppressed=False,
            )
        )
        session.commit()

        hit = try_resolve_geocode_cache(
            session,
            project_id=pid,
            stylebook_id=sb_id,
            location_text="Chicago, IL",
            location_type="city",
        )
    assert hit is not None
    assert hit["confidence"]["source"] == "canonical_db"
    assert hit["id"] == cid
    assert hit["boundaries"] == [gj]


def test_try_resolve_inexact_strings_miss_tier1_canonical() -> None:
    """Tier 1 is exact normalized label/alias only — no fuzzy parent matches."""
    gj = {"type": "Point", "coordinates": [-87.0, 41.0]}
    for loc_text in (
        "Uptown, Chicago, IL",
        "Uptown Chicago IL",
        "Chatham, Chicago, IL",
    ):
        engine = _engine()
        with Session(engine) as session:
            pid, sb_id, _ = _seed_org_sb_project(session)
            c = StylebookLocationCanonical(
                stylebook_id=sb_id,
                label="Chicago, IL",
                slug="chicago-il",
                location_type="city",
                status="active",
                geometry_json=gj,
                geometry_type="Point",
            )
            session.add(c)
            session.commit()
            session.refresh(c)
            cid = str(c.id)
            session.add(
                StylebookLocationAlias(
                    location_canonical_id=cid,
                    alias_text="Chicago, IL",
                    normalized_alias="chicago, il",
                    provenance="test",
                    suppressed=False,
                )
            )
            session.commit()

            hit = try_resolve_geocode_cache(
                session,
                project_id=pid,
                stylebook_id=sb_id,
                location_text=loc_text,
                location_type="neighborhood",
            )
        assert hit is None, loc_text


def test_try_resolve_chicago_il_without_comma_misses_label_with_comma() -> None:
    """Punctuation variant: misses unless an alias normalizes the same way."""
    gj = {"type": "Point", "coordinates": [-87.0, 41.0]}
    engine = _engine()
    with Session(engine) as session:
        pid, sb_id, _ = _seed_org_sb_project(session)
        c = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            status="active",
            geometry_json=gj,
            geometry_type="Point",
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        cid = str(c.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="Chicago, IL",
                normalized_alias="chicago, il",
                provenance="test",
                suppressed=False,
            )
        )
        session.commit()

        hit = try_resolve_geocode_cache(
            session,
            project_id=pid,
            stylebook_id=sb_id,
            location_text="Chicago IL",
            location_type="city",
        )
    assert hit is None


def test_ambiguous_tier1_skips_substrate_tier2() -> None:
    """Ambiguous exact tier-1 must not fall through to fingerprint tier-2."""
    gj = {"type": "Point", "coordinates": [-87.0, 41.0]}
    engine = _engine()
    with Session(engine) as session:
        pid, sb_id, _ = _seed_org_sb_project(session)
        c1 = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            status="active",
            geometry_json=gj,
            geometry_type="Point",
        )
        c2 = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, Illinois",
            slug="chicago-illinois",
            location_type="city",
            status="active",
            geometry_json=gj,
            geometry_type="Point",
        )
        session.add(c1)
        session.add(c2)
        session.commit()
        session.refresh(c1)
        session.refresh(c2)
        for c in (c1, c2):
            cid = str(c.id)
            session.add(
                StylebookLocationAlias(
                    location_canonical_id=cid,
                    alias_text="Chicago, IL",
                    normalized_alias="chicago, il",
                    provenance="test",
                    suppressed=False,
                )
            )
        fp = substrate_location_cache_query_fingerprint(
            project_id=pid,
            normalized_query="chicago, il",
            location_type="city",
        )
        session.add(
            SubstrateLocationCache(
                project_id=pid,
                query_text="Chicago, IL",
                normalized_query="chicago, il",
                query_fingerprint=fp,
                location_name="Chicago, IL",
                location_type="city",
                geocode_type="pelias",
                formatted_address="Chicago, IL, USA",
                geometry_json=gj,
                geometry_type="Point",
                response_payload_json={},
            )
        )
        session.commit()

        hit = try_resolve_geocode_cache(
            session,
            project_id=pid,
            stylebook_id=sb_id,
            location_text="Chicago, IL",
            location_type="city",
        )
    assert hit is None


def test_try_resolve_neighborhood_extract_blocks_city_canonical_tier1() -> None:
    """Extractor type incompatible with canonical must not auto-hit tier 1."""
    gj = {"type": "Point", "coordinates": [-87.0, 41.0]}
    engine = _engine()
    with Session(engine) as session:
        pid, sb_id, _ = _seed_org_sb_project(session)
        c = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            status="active",
            geometry_json=gj,
            geometry_type="Point",
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        cid = str(c.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="Chicago, IL",
                normalized_alias="chicago, il",
                provenance="test",
                suppressed=False,
            )
        )
        session.commit()

        hit = try_resolve_geocode_cache(
            session,
            project_id=pid,
            stylebook_id=sb_id,
            location_text="Chicago, IL",
            location_type="neighborhood",
        )
    assert hit is None


def test_tier2_sanity_rejects_state_mismatch() -> None:
    engine = _engine()
    with Session(engine) as session:
        pid, sb_id, _ = _seed_org_sb_project(session)
        gj = {"type": "Point", "coordinates": [-88.0, 42.0]}
        fp = substrate_location_cache_query_fingerprint(
            project_id=pid,
            normalized_query=normalize_substrate_cache_query("Rockford, IL"),
            location_type="city",
        )
        session.add(
            SubstrateLocationCache(
                project_id=pid,
                query_text="Rockford, IL",
                normalized_query=normalize_substrate_cache_query("Rockford, IL"),
                query_fingerprint=fp,
                location_name="Rockford, IL",
                location_type="city",
                geocode_type="pelias",
                formatted_address="Rockford, IL, USA",
                geometry_json=gj,
                geometry_type="Point",
                response_payload_json={},
            )
        )
        session.commit()

        outcome = resolve_geocode_cache_strict_with_outcome(
            session,
            project_id=pid,
            stylebook_id=sb_id,
            location_text="Rockford, IL",
            location_type="city",
            components={"state": {"abbr": "NE"}},
        )
    assert outcome.match_dict is None
    assert outcome.tier2_sanity_failed is True


def test_materialize_canonical_match_dict_active_only() -> None:
    gj = {"type": "Point", "coordinates": [-87.0, 41.0]}
    engine = _engine()
    with Session(engine) as session:
        _, sb_id, _ = _seed_org_sb_project(session)
        c = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            status="active",
            geometry_json=gj,
            geometry_type="Point",
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        cid = str(c.id)
        md = materialize_canonical_match_dict(session, stylebook_id=sb_id, canonical_id=cid)
    assert md is not None
    assert md["confidence"]["source"] == "canonical_db"


def test_build_adjudication_candidates_includes_canonical() -> None:
    gj = {"type": "Point", "coordinates": [-87.0, 41.0]}
    engine = _engine()
    with Session(engine) as session:
        _, sb_id, _ = _seed_org_sb_project(session)
        c = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            status="active",
            geometry_json=gj,
            geometry_type="Point",
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        cid = str(c.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="Chicago, IL",
                normalized_alias="chicago, il",
                provenance="test",
                suppressed=False,
            )
        )
        session.commit()

        cands = build_geocode_cache_adjudication_candidates(
            session,
            stylebook_id=sb_id,
            location_text="Chicago, IL",
            location_type="city",
            components=None,
            limit=10,
        )
    assert len(cands) >= 1
    ids = {str(x["id"]) for x in cands}
    assert cid in ids


def test_city_substrate_blocks_political_district_canonical_tier1() -> None:
    """City-level query must not strict-hit an electoral ward canonical."""
    gj = {"type": "MultiPolygon", "coordinates": []}
    engine = _engine()
    with Session(engine) as session:
        pid, sb_id, _ = _seed_org_sb_project(session)
        ward = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Ward 15, Chicago, IL",
            slug="ward-15-chicago",
            location_type="political_district",
            status="active",
            geometry_json=gj,
            geometry_type="MultiPolygon",
            formatted_address="Ward 15, Chicago, IL",
        )
        session.add(ward)
        session.commit()
        session.refresh(ward)
        wid = str(ward.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=wid,
                alias_text="Chicago, IL",
                normalized_alias="chicago, il",
                provenance="test",
                suppressed=False,
            )
        )
        session.commit()

        hit = try_resolve_geocode_cache(
            session,
            project_id=pid,
            stylebook_id=sb_id,
            location_text="Chicago, IL",
            location_type="city",
        )
    assert hit is None


def test_city_substrate_blocks_ward_like_label_even_when_canonical_type_city() -> None:
    """Mis-typed city rows whose label is ward-shaped must not auto-hit for municipality queries."""
    gj = {"type": "MultiPolygon", "coordinates": []}
    engine = _engine()
    with Session(engine) as session:
        pid, sb_id, _ = _seed_org_sb_project(session)
        w = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Ward 15, Chicago, IL",
            slug="ward15-chicago-mislabeled",
            location_type="city",
            status="active",
            geometry_json=gj,
            geometry_type="MultiPolygon",
        )
        session.add(w)
        session.commit()
        session.refresh(w)
        wid = str(w.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=wid,
                alias_text="Chicago, IL",
                normalized_alias="chicago, il",
                provenance="test",
                suppressed=False,
            )
        )
        session.commit()

        hit = try_resolve_geocode_cache(
            session,
            project_id=pid,
            stylebook_id=sb_id,
            location_text="Chicago, IL",
            location_type="city",
        )
    assert hit is None


def test_city_tier2_rejects_ward_shaped_substrate_row() -> None:
    engine = _engine()
    with Session(engine) as session:
        pid, sb_id, _ = _seed_org_sb_project(session)
        gj = {"type": "MultiPolygon", "coordinates": []}
        fp = substrate_location_cache_query_fingerprint(
            project_id=pid,
            normalized_query="chicago, il",
            location_type="city",
        )
        session.add(
            SubstrateLocationCache(
                project_id=pid,
                query_text="Chicago, IL",
                normalized_query="chicago, il",
                query_fingerprint=fp,
                location_name="Chicago, IL",
                location_type="city",
                geocode_type="pelias",
                formatted_address="Ward 15, Chicago, IL",
                geometry_json=gj,
                geometry_type="MultiPolygon",
                response_payload_json={},
            )
        )
        session.commit()

        outcome = resolve_geocode_cache_strict_with_outcome(
            session,
            project_id=pid,
            stylebook_id=sb_id,
            location_text="Chicago, IL",
            location_type="city",
            components=None,
        )
    assert outcome.match_dict is None
    assert outcome.tier2_sanity_failed is True


def test_materialize_rejects_ward_for_city_substrate() -> None:
    gj = {"type": "MultiPolygon", "coordinates": []}
    engine = _engine()
    with Session(engine) as session:
        _, sb_id, _ = _seed_org_sb_project(session)
        ward = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Ward 15, Chicago, IL",
            slug="ward-15",
            location_type="political_district",
            status="active",
            geometry_json=gj,
            geometry_type="MultiPolygon",
        )
        session.add(ward)
        session.commit()
        session.refresh(ward)
        wid = str(ward.id)
        md = materialize_canonical_match_dict(
            session,
            stylebook_id=sb_id,
            canonical_id=wid,
            substrate_location_type="city",
        )
    assert md is None


def test_build_candidates_excludes_ward_for_city_query() -> None:
    gj_city = {"type": "Point", "coordinates": [-87.0, 41.0]}
    gj_ward = {"type": "MultiPolygon", "coordinates": []}
    engine = _engine()
    with Session(engine) as session:
        _, sb_id, _ = _seed_org_sb_project(session)
        city = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            status="active",
            geometry_json=gj_city,
            geometry_type="Point",
        )
        ward = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Ward 99, Chicago, IL",
            slug="ward-99",
            location_type="political_district",
            status="active",
            geometry_json=gj_ward,
            geometry_type="MultiPolygon",
        )
        session.add(city)
        session.add(ward)
        session.commit()
        session.refresh(city)
        session.refresh(ward)
        cid_city = str(city.id)
        cid_ward = str(ward.id)
        for cid in (cid_city, cid_ward):
            session.add(
                StylebookLocationAlias(
                    location_canonical_id=cid,
                    alias_text="Chicago, IL",
                    normalized_alias="chicago, il",
                    provenance="test",
                    suppressed=False,
                )
            )
        session.commit()

        cands = build_geocode_cache_adjudication_candidates(
            session,
            stylebook_id=sb_id,
            location_text="Chicago, IL",
            location_type="city",
            limit=20,
        )
    ids = {str(x["id"]) for x in cands}
    assert cid_city in ids
    assert cid_ward not in ids


def test_try_resolve_ambiguous_two_canonicals_returns_none() -> None:
    """Two canonicals both match the same normalized string → ambiguous tier-1 → miss."""
    gj = {"type": "Point", "coordinates": [-87.0, 41.0]}
    engine = _engine()
    with Session(engine) as session:
        pid, sb_id, _ = _seed_org_sb_project(session)
        c1 = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            status="active",
            geometry_json=gj,
            geometry_type="Point",
        )
        c2 = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, Illinois",
            slug="chicago-illinois",
            location_type="city",
            status="active",
            geometry_json=gj,
            geometry_type="Point",
        )
        session.add(c1)
        session.add(c2)
        session.commit()
        session.refresh(c1)
        session.refresh(c2)
        for c in (c1, c2):
            cid = str(c.id)
            session.add(
                StylebookLocationAlias(
                    location_canonical_id=cid,
                    alias_text="Chicago, IL",
                    normalized_alias="chicago, il",
                    provenance="test",
                    suppressed=False,
                )
            )
        session.commit()

        hit = try_resolve_geocode_cache(
            session,
            project_id=pid,
            stylebook_id=sb_id,
            location_text="Chicago, IL",
            location_type="city",
        )
    assert hit is None


def test_try_resolve_substrate_cache_tier2() -> None:
    engine = _engine()
    with Session(engine) as session:
        pid, sb_id, _ = _seed_org_sb_project(session)
        gj = {"type": "Point", "coordinates": [-88.0, 42.0]}
        fp = substrate_location_cache_query_fingerprint(
            project_id=pid,
            normalized_query=normalize_substrate_cache_query("Rockford, IL"),
            location_type="city",
        )
        session.add(
            SubstrateLocationCache(
                project_id=pid,
                query_text="Rockford, IL",
                normalized_query=normalize_substrate_cache_query("Rockford, IL"),
                query_fingerprint=fp,
                location_name="Rockford, IL",
                location_type="city",
                geocode_type="pelias",
                formatted_address="Rockford, IL, USA",
                geometry_json=gj,
                geometry_type="Point",
                response_payload_json={},
            )
        )
        session.commit()

        hit = try_resolve_geocode_cache(
            session,
            project_id=pid,
            stylebook_id=sb_id,
            location_text="Rockford, IL",
            location_type="city",
        )
    assert hit is not None
    assert hit["confidence"]["source"] == "location_cache"
    assert hit["label"] == "Rockford, IL"


def test_address_tier2_rejects_city_only_poisoned_row() -> None:
    """Tier-2 substrate cache must not return city geometry for a street address query."""
    engine = _engine()
    with Session(engine) as session:
        pid, sb_id, _ = _seed_org_sb_project(session)
        query = "500 N. Franklin St., Chicago, IL"
        fp = substrate_location_cache_query_fingerprint(
            project_id=pid,
            normalized_query=normalize_substrate_cache_query(query),
            location_type="address",
        )
        session.add(
            SubstrateLocationCache(
                project_id=pid,
                query_text=query,
                normalized_query=normalize_substrate_cache_query(query),
                query_fingerprint=fp,
                location_name="Chicago, IL",
                location_type="city",
                geocode_type="stylebook",
                formatted_address="Chicago, IL",
                geometry_json={
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-87.94, 41.64],
                            [-87.52, 41.64],
                            [-87.52, 42.02],
                            [-87.94, 42.02],
                            [-87.94, 41.64],
                        ]
                    ],
                },
                geometry_type="Polygon",
                response_payload_json={},
            )
        )
        session.commit()

        outcome = resolve_geocode_cache_strict_with_outcome(
            session,
            project_id=pid,
            stylebook_id=sb_id,
            location_text=query,
            location_type="address",
            components={
                "address": "500 N. Franklin St.",
                "city": "Chicago",
                "state": {"abbr": "IL"},
            },
        )
    assert outcome.match_dict is None
    assert outcome.tier2_sanity_failed is True


def test_address_tier1_blocks_city_canonical_even_with_exact_alias() -> None:
    """Exact alias on a city canonical must not auto-hit for a street-address extract."""
    gj = {
        "type": "Polygon",
        "coordinates": [
            [[-88.0, 41.0], [-87.0, 41.0], [-87.0, 42.0], [-88.0, 42.0], [-88.0, 41.0]]
        ],
    }
    engine = _engine()
    with Session(engine) as session:
        pid, sb_id, _ = _seed_org_sb_project(session)
        c = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            status="active",
            geometry_json=gj,
            geometry_type="Polygon",
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        cid = str(c.id)
        poisoned_query = normalize_substrate_cache_query("500 N. Franklin St., Chicago, IL")
        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="500 N. Franklin St., Chicago, IL",
                normalized_alias=poisoned_query,
                provenance="test",
                suppressed=False,
            )
        )
        session.commit()

        hit = try_resolve_geocode_cache(
            session,
            project_id=pid,
            stylebook_id=sb_id,
            location_text="500 N. Franklin St., Chicago, IL",
            location_type="address",
            components={"address": "500 N. Franklin St.", "state": {"abbr": "IL"}},
        )
    assert hit is None


def test_tier1_ignores_substrate_ingest_alias_poison() -> None:
    """Machine-written aliases must not produce tier-1 exact geocode hits."""
    gj = {
        "type": "Polygon",
        "coordinates": [
            [[-87.7, 41.9], [-87.65, 41.9], [-87.65, 41.93], [-87.7, 41.93], [-87.7, 41.9]]
        ],
    }
    engine = _engine()
    with Session(engine) as session:
        pid, sb_id, _ = _seed_org_sb_project(session)
        bucktown = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Bucktown, Chicago, IL",
            slug="bucktown-chicago-il",
            location_type="neighborhood",
            status="active",
            geometry_json=gj,
            geometry_type="Polygon",
        )
        session.add(bucktown)
        session.commit()
        session.refresh(bucktown)
        cid = str(bucktown.id)
        poisoned = normalize_substrate_cache_query("Uptown, Chicago, IL")
        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="Uptown, Chicago, IL",
                normalized_alias=poisoned,
                provenance="substrate_ingest",
                suppressed=False,
            )
        )
        session.commit()

        hit = try_resolve_geocode_cache(
            session,
            project_id=pid,
            stylebook_id=sb_id,
            location_text="Uptown, Chicago, IL",
            location_type="neighborhood",
            components={"neighborhood": "Uptown", "city": "Chicago"},
        )
    assert hit is None


def test_tier1_allows_editorial_alias_for_neighborhood() -> None:
    gj = {
        "type": "Polygon",
        "coordinates": [
            [[-87.7, 41.9], [-87.65, 41.9], [-87.65, 41.93], [-87.7, 41.93], [-87.7, 41.9]]
        ],
    }
    engine = _engine()
    with Session(engine) as session:
        pid, sb_id, _ = _seed_org_sb_project(session)
        uptown = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Uptown, Chicago, IL",
            slug="uptown-chicago-il",
            location_type="neighborhood",
            status="active",
            geometry_json=gj,
            geometry_type="Polygon",
            formatted_address="Uptown, Chicago, IL",
        )
        session.add(uptown)
        session.commit()
        session.refresh(uptown)
        cid = str(uptown.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="Uptown, Chicago, IL",
                normalized_alias=normalize_substrate_cache_query("Uptown, Chicago, IL"),
                provenance="stylebook_ui_accept",
                suppressed=False,
            )
        )
        session.commit()

        hit = try_resolve_geocode_cache(
            session,
            project_id=pid,
            stylebook_id=sb_id,
            location_text="Uptown, Chicago, IL",
            location_type="neighborhood",
            components={"neighborhood": "Uptown", "city": "Chicago"},
        )
    assert hit is not None
    assert hit.get("id") == cid
    conf = hit.get("confidence")
    assert isinstance(conf, dict)
    assert conf.get("canonical_id") == cid
