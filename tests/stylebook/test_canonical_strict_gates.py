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
    strict_canonical_gates_enabled,
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
