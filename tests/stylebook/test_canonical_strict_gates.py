"""Deterministic canonical autolink gates (type, container/POI, jurisdiction, geocode QA)."""

from __future__ import annotations

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldWorkspace,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_stylebook.bootstrap import ensure_default_stylebook_for_organization
from backfield_stylebook.canonical_jurisdiction import (
    container_admin_query_from_components,
    geocode_components_vs_formatted_address_mismatch,
    jurisdiction_from_components,
    parse_jurisdiction_from_formatted_address,
    strict_canonical_gates_enabled,
)
from backfield_stylebook.entities.location.policy import (
    _jurisdiction_pair_demotes_recall_score,
    find_existing_canonical_id_by_normalized_label,
)
from backfield_stylebook.canonical_link_matrix import (
    autolink_container_to_fine_denied,
    link_pair_allowed,
)
from backfield_stylebook.canonical_policy import decide_canonical_persist_plan
from sqlmodel import Session, SQLModel, create_engine


@pytest.mark.parametrize(
    ("s", "c", "expect"),
    [
        ("state", "place", False),
        ("state", "neighborhood", False),
        ("country", "place", False),
        ("region_national", "address", False),
        ("county", "place", False),
        ("city", "state", False),
        ("state", "town", False),
        ("village", "region_state", False),
        ("region_state", "city", False),
        ("city", "county", False),
        ("county", "city", False),
        ("town", "county", False),
        ("city", "neighborhood", False),
        ("neighborhood", "city", False),
        ("town", "neighborhood", False),
        ("village", "neighborhood", False),
        ("street_road", "neighborhood", False),
        ("neighborhood", "intersection_road", False),
        ("span", "neighborhood", False),
        ("city", "region_city", False),
        ("region_city", "town", False),
        ("region_city", "street_road", False),
        ("span", "region_city", False),
        ("place", "street_road", False),
        ("street_road", "point", False),
        # Mitigations 3: linear ↔ municipality, place ↔ neighborhood / region_city,
        # neighborhood ↔ region_city.
        ("street_road", "city", False),
        ("city", "street_road", False),
        ("street_road", "town", False),
        ("town", "street_road", False),
        ("intersection_road", "city", False),
        ("city", "intersection_road", False),
        ("intersection_road", "town", False),
        ("town", "intersection_road", False),
        ("intersection_highway", "city", False),
        ("city", "intersection_highway", False),
        ("intersection_highway", "town", False),
        ("town", "intersection_highway", False),
        ("span", "city", False),
        ("city", "span", False),
        ("span", "town", False),
        ("town", "span", False),
        ("place", "neighborhood", False),
        ("neighborhood", "place", False),
        ("intersection_road", "place", False),
        ("intersection_road", "point", False),
        ("intersection_highway", "neighborhood", False),
        ("place", "region_city", False),
        ("region_city", "place", False),
        ("neighborhood", "region_city", False),
        ("region_city", "neighborhood", False),
        ("place", "city", False),
        ("city", "place", False),
        ("point", "city", False),
        ("town", "point", False),
        ("village", "place", False),
        ("city", "city", True),
        ("place", "place", True),
        ("region_city", "region_city", True),
        ("city", "political_district", False),
        ("political_district", "city", False),
        ("town", "political_district", False),
    ],
)
def test_link_pair_allowed_deny_list(s: str, c: str, expect: bool) -> None:
    assert link_pair_allowed(s, c) is expect


@pytest.mark.parametrize(
    ("s", "c", "expect"),
    [
        ("city", "place", True),
        ("county", "neighborhood", True),
        ("town", "address", True),
        ("region_city", "place", True),
        ("neighborhood", "place", False),
        ("city", "city", False),
    ],
)
def test_autolink_container_to_fine_denied(s: str, c: str, expect: bool) -> None:
    assert autolink_container_to_fine_denied(s, c) is expect


def test_jurisdiction_from_components_round_trip() -> None:
    comps = {
        "city": "Skokie",
        "state": {"abbr": "IL"},
        "country": {"abbr": "US"},
    }
    assert jurisdiction_from_components(comps) == ("US", "IL", "Skokie")
    assert container_admin_query_from_components(comps) == "Skokie, IL, US"


def test_geocode_components_vs_formatted_address_mismatch() -> None:
    comps = {"state": {"abbr": "IL"}, "country": {"abbr": "US"}, "city": "Chicago"}
    assert geocode_components_vs_formatted_address_mismatch(
        formatted_address="Chicago, IL, USA",
        comps=comps,
    ) is None
    assert (
        geocode_components_vs_formatted_address_mismatch(
            formatted_address="Chicago, IN, USA",
            comps=comps,
        )
        == "geocode_state_mismatch"
    )


def test_parse_jurisdiction_from_formatted_address_state_with_zip() -> None:
    assert parse_jurisdiction_from_formatted_address(
        "Tonia Rd, Arkadelphia, AR 71923"
    ) == ("US", "AR")


def test_geocode_country_mismatch_when_story_is_abroad() -> None:
    comps = {
        "city": "Aksum",
        "state": None,
        "country": {"name": "Ethiopia", "abbr": "ET"},
    }
    assert (
        geocode_components_vs_formatted_address_mismatch(
            formatted_address="Tonia Rd, Arkadelphia, AR 71923",
            comps=comps,
        )
        == "geocode_country_mismatch"
    )


def _make_engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _bootstrap(session: Session, *, org_slug: str) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug=org_slug)
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = ensure_default_stylebook_for_organization(session, oid)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    ws = BackfieldWorkspace(
        organization_id=oid, stylebook_id=sb_id, name="W", slug=f"wg-{org_slug}"
    )
    session.add(ws)
    session.commit()
    return oid, sb_id


def test_decide_links_imported_canonical_by_normalized_label_without_alias(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bundle-imported rows without aliases still link when label matches tier-1 rules."""
    monkeypatch.setenv("BACKFIELD_STRICT_CANONICAL_GATES", "1")
    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="strict-gates-label")
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Albany Park, Chicago, IL",
            slug="albany-park-chicago-il",
            location_type="neighborhood",
            status="active",
            geometry_json={"type": "Point", "coordinates": [-87.72, 41.97]},
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        loc = SubstrateLocation(
            project_id=1,
            name="Albany Park, Chicago, IL",
            normalized_name="albany park, chicago, il",
            location_type="neighborhood",
            status="resolved",
            canonical_link_status="unlinked",
            formatted_address="Albany Park, Chicago, IL",
            source_details_json={
                "place_extract_components": {
                    "neighborhood": "Albany Park",
                    "city": "Chicago",
                    "state": {"abbr": "IL"},
                    "country": {"abbr": "US"},
                }
            },
            geometry_json={"type": "Point", "coordinates": [-87.72, 41.97]},
            identity_fingerprint="fp-strict-label",
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)
        assert find_existing_canonical_id_by_normalized_label(
            session, stylebook_id=sb_id, location=loc
        ) == str(canon.id)
        plan = decide_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            places_bucket="areas.neighborhoods",
            location=loc,
            entry={"components": loc.source_details_json["place_extract_components"]},
        )
        assert plan.decision.value == "link_existing"
        assert plan.existing_canonical_id == str(canon.id)
        assert any(
            isinstance(r, dict) and r.get("code") == "linked_exact_normalized_label"
            for r in plan.resolution_reasons
        )


def test_decide_preflight_defers_on_geocode_country_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKFIELD_STRICT_CANONICAL_GATES", "1")
    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="strict-gates-country")
        loc = SubstrateLocation(
            project_id=1,
            name="Aksum, Tigray, Ethiopia",
            normalized_name="aksum, tigray, ethiopia",
            location_type="place",
            status="resolved",
            canonical_link_status="unlinked",
            formatted_address="Tonia Rd, Arkadelphia, AR 71923",
            source_details_json={
                "place_extract_components": {
                    "city": "Aksum",
                    "state": None,
                    "country": {"name": "Ethiopia", "abbr": "ET"},
                }
            },
            geometry_json={"type": "Point", "coordinates": [-93.05, 34.12]},
            identity_fingerprint="fp-strict-country",
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)
        plan = decide_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            places_bucket="points",
            location=loc,
            entry={"components": loc.source_details_json["place_extract_components"]},
        )
        assert plan.decision.value == "defer"
        assert any(
            isinstance(r, dict) and r.get("code") == "geocode_country_mismatch"
            for r in plan.resolution_reasons
        )


def test_jurisdiction_pair_demotes_on_country_without_state() -> None:
    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="strict-gates-jur-country")
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Tonia Rd, Arkadelphia, AR",
            slug="tonia-rd",
            location_type="address",
            country_code="US",
            subdivision_code="AR",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        loc = SubstrateLocation(
            project_id=1,
            name="Aksum, Tigray, Ethiopia",
            normalized_name="aksum, tigray, ethiopia",
            location_type="place",
            status="resolved",
            canonical_link_status="unlinked",
            identity_fingerprint="fp-jur-country",
        )
        comps = {
            "city": "Aksum",
            "country": {"abbr": "ET"},
        }
        assert _jurisdiction_pair_demotes_recall_score(loc, canon, comps) is True


def test_decide_preflight_defers_on_geocode_state_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKFIELD_STRICT_CANONICAL_GATES", "1")
    assert strict_canonical_gates_enabled() is True
    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="strict-gates-1")
        loc = SubstrateLocation(
            project_id=1,
            name="Test Place, Chicago, IL",
            normalized_name="test place, chicago, il",
            location_type="place",
            status="resolved",
            canonical_link_status="unlinked",
            formatted_address="Test Place, Chicago, IN, USA",
            source_details_json={
                "place_extract_components": {
                    "city": "Chicago",
                    "state": {"abbr": "IL"},
                    "country": {"abbr": "US"},
                }
            },
            geometry_json={"type": "Point", "coordinates": [-87.6, 41.9]},
            identity_fingerprint="fp-strict-1",
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)
        plan = decide_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            places_bucket="points",
            location=loc,
            entry={"components": loc.source_details_json["place_extract_components"]},
        )
        assert plan.decision.value == "defer"
        assert any(
            isinstance(r, dict) and r.get("code") == "geocode_state_mismatch"
            for r in plan.resolution_reasons
        )


def test_decide_city_does_not_autolink_to_place_canonical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKFIELD_STRICT_CANONICAL_GATES", "1")
    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="strict-gates-2")
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Deerfield High School, Deerfield, IL",
            slug="deerfield-hs",
            location_type="place",
            subdivision_code="IL",
            country_code="US",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        loc = SubstrateLocation(
            project_id=1,
            name="Deerfield, IL",
            normalized_name="deerfield, il",
            location_type="city",
            status="resolved",
            canonical_link_status="unlinked",
            formatted_address="Deerfield, IL, USA",
            source_details_json={
                "place_extract_components": {
                    "city": "Deerfield",
                    "state": {"abbr": "IL"},
                    "country": {"abbr": "US"},
                }
            },
            geometry_json={"type": "Point", "coordinates": [-87.84, 42.17]},
            identity_fingerprint="fp-strict-2",
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)
        plan = decide_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            places_bucket="areas.cities",
            location=loc,
            entry={"components": loc.source_details_json["place_extract_components"]},
        )
        assert plan.existing_canonical_id != str(canon.id)
