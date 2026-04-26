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
from backfield_stylebook.bootstrap import ensure_default_stylebook_for_organization
from backfield_stylebook.geocode_cache_resolve import try_resolve_geocode_cache
from backfield_stylebook.substrate_location_cache_fingerprint import (
    normalize_substrate_cache_query,
    substrate_location_cache_query_fingerprint,
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
