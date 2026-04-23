"""Tests for the canonical type compatibility gate.

The gate prevents substrate locations from autolinking to canonicals whose
``location_type`` belongs to a different strict group (state, city, county,
neighborhood).  Flexible types (address, place, intersection, region_city, etc.)
can match each other and can also match canonicals with no type set.
"""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldWorkspace,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_stylebook.bootstrap import ensure_default_stylebook_for_organization
from backfield_stylebook.canonical_policy import (
    CanonicalPersistDecision,
    rank_scored_canonical_recall_matches,
    types_are_autolink_compatible,
)
from sqlmodel import Session, SQLModel, create_engine

# ---------------------------------------------------------------------------
# Pure unit tests for types_are_autolink_compatible (no DB)
# ---------------------------------------------------------------------------


def test_city_to_city_compatible() -> None:
    assert types_are_autolink_compatible("city", "city") is True


def test_town_to_city_compatible() -> None:
    # town and city share the same strict group
    assert types_are_autolink_compatible("town", "city") is True


def test_city_to_town_compatible() -> None:
    assert types_are_autolink_compatible("city", "town") is True


def test_state_to_state_compatible() -> None:
    assert types_are_autolink_compatible("state", "state") is True


def test_region_state_to_state_compatible() -> None:
    assert types_are_autolink_compatible("region_state", "state") is True


def test_county_to_county_compatible() -> None:
    assert types_are_autolink_compatible("county", "county") is True


def test_neighborhood_to_neighborhood_compatible() -> None:
    assert types_are_autolink_compatible("neighborhood", "neighborhood") is True


def test_community_area_to_neighborhood_compatible() -> None:
    assert types_are_autolink_compatible("community_area", "neighborhood") is True


def test_country_to_country_compatible() -> None:
    assert types_are_autolink_compatible("country", "country") is True


# Cross-strict-group mismatches must be blocked
def test_address_to_city_incompatible() -> None:
    assert types_are_autolink_compatible("address", "city") is False


def test_intersection_road_to_city_incompatible() -> None:
    assert types_are_autolink_compatible("intersection_road", "city") is False


def test_intersection_highway_to_city_incompatible() -> None:
    assert types_are_autolink_compatible("intersection_highway", "city") is False


def test_place_to_city_incompatible() -> None:
    assert types_are_autolink_compatible("place", "city") is False


def test_region_city_to_city_incompatible() -> None:
    # region_city (ward-like) is flexible; city canonical is strict
    assert types_are_autolink_compatible("region_city", "city") is False


def test_neighborhood_to_city_incompatible() -> None:
    assert types_are_autolink_compatible("neighborhood", "city") is False


def test_city_to_state_incompatible() -> None:
    assert types_are_autolink_compatible("city", "state") is False


def test_city_to_county_incompatible() -> None:
    assert types_are_autolink_compatible("city", "county") is False


def test_county_to_state_incompatible() -> None:
    assert types_are_autolink_compatible("county", "state") is False


def test_neighborhood_to_county_incompatible() -> None:
    assert types_are_autolink_compatible("neighborhood", "county") is False


# Flexible types are compatible with each other and with untyped canonicals
def test_address_to_place_compatible() -> None:
    assert types_are_autolink_compatible("address", "place") is True


def test_place_to_address_compatible() -> None:
    assert types_are_autolink_compatible("place", "address") is True


def test_intersection_to_address_compatible() -> None:
    assert types_are_autolink_compatible("intersection_road", "address") is True


def test_region_city_to_none_compatible() -> None:
    # Canonical with no type set — flexible
    assert types_are_autolink_compatible("region_city", None) is True


def test_address_to_none_compatible() -> None:
    assert types_are_autolink_compatible("address", None) is True


def test_city_to_none_compatible() -> None:
    # Canonical has no type: can't gate on unknown
    assert types_are_autolink_compatible("city", None) is True


def test_none_substrate_to_city_canonical_compatible() -> None:
    # Substrate with no type: can't gate on unknown substrate
    assert types_are_autolink_compatible(None, "city") is True


def test_natural_to_natural_compatible() -> None:
    assert types_are_autolink_compatible("natural", "natural") is True


def test_natural_to_city_incompatible() -> None:
    # natural is flexible; city canonical is strict
    assert types_are_autolink_compatible("natural", "city") is False


# ---------------------------------------------------------------------------
# Integration test: rank_scored_canonical_recall_matches applies the gate
# ---------------------------------------------------------------------------


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
        organization_id=oid, stylebook_id=sb_id, name="W", slug=f"ws-{org_slug}"
    )
    session.add(ws)
    session.commit()
    return oid, sb_id


def test_rank_caps_incompatible_type_below_recall() -> None:
    """An address substrate must not autolink to a city canonical via the scorer."""
    from backfield_stylebook.canonical_match_score import AUTOLINK_MIN_SCORE, RECALL_MIN_SCORE

    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg1")

        # Canonical is a city
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            location_type="city",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = int(canon.id)  # type: ignore[arg-type]

        alias = StylebookLocationAlias(
            location_canonical_id=cid,
            alias_text="Chicago, IL",
            normalized_alias="chicago, il",
            provenance="test",
            suppressed=False,
        )
        session.add(alias)
        session.commit()

        # Substrate is an address that happens to end with ", Chicago, IL"
        loc = SubstrateLocation(
            project_id=1,
            name="1020 W. Sheridan Road, Chicago, IL",
            normalized_name="1020 w. sheridan road, chicago, il",
            location_type="address",
            formatted_address="1020 West Sheridan Road, North Side, Chicago, IL, USA",
            identity_fingerprint="fp-type-gate-1",
        )

        # SQLite has no pg_trgm hints; pass None as the retrieval hint.
        ranked = rank_scored_canonical_recall_matches(
            session,
            location=loc,
            recall=[(cid, None)],
        )

    assert len(ranked) == 1
    _, _label, score, _ = ranked[0]
    assert score < RECALL_MIN_SCORE, (
        f"Expected address→city score below RECALL_MIN_SCORE ({RECALL_MIN_SCORE}), got {score}"
    )
    assert score < AUTOLINK_MIN_SCORE


def test_rank_allows_same_type_city_to_city() -> None:
    """A city substrate should score normally against a city canonical."""
    from backfield_stylebook.canonical_match_score import AUTOLINK_MIN_SCORE

    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg2")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            location_type="city",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = int(canon.id)  # type: ignore[arg-type]

        alias = StylebookLocationAlias(
            location_canonical_id=cid,
            alias_text="Chicago, IL",
            normalized_alias="chicago, il",
            provenance="test",
            suppressed=False,
        )
        session.add(alias)
        session.commit()

        loc = SubstrateLocation(
            project_id=1,
            name="Chicago, IL",
            normalized_name="chicago, il",
            location_type="city",
            identity_fingerprint="fp-type-gate-2",
        )

        ranked = rank_scored_canonical_recall_matches(
            session,
            location=loc,
            recall=[(cid, None)],
        )

    assert len(ranked) == 1
    _, _label, score, _ = ranked[0]
    assert score >= AUTOLINK_MIN_SCORE, (
        f"Expected city→city score >= AUTOLINK_MIN_SCORE ({AUTOLINK_MIN_SCORE}), got {score}"
    )


def test_rank_caps_intersection_to_city() -> None:
    """An intersection substrate must not autolink to a city canonical."""
    from backfield_stylebook.canonical_match_score import RECALL_MIN_SCORE

    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg3")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            location_type="city",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = int(canon.id)  # type: ignore[arg-type]

        alias = StylebookLocationAlias(
            location_canonical_id=cid,
            alias_text="Chicago, IL",
            normalized_alias="chicago, il",
            provenance="test",
            suppressed=False,
        )
        session.add(alias)
        session.commit()

        loc = SubstrateLocation(
            project_id=1,
            name="Illinois St. and Clark St., Chicago, IL",
            normalized_name="illinois st. and clark st., chicago, il",
            location_type="intersection_road",
            formatted_address="N Clark St and W Illinois St, Chicago, IL 60654",
            identity_fingerprint="fp-type-gate-3",
        )

        ranked = rank_scored_canonical_recall_matches(
            session,
            location=loc,
            recall=[(cid, None)],
        )

    assert len(ranked) == 1
    _, _label, score, _ = ranked[0]
    assert score < RECALL_MIN_SCORE


def test_rank_allows_address_to_place() -> None:
    """An address substrate should be allowed to score against a place canonical."""
    from backfield_stylebook.canonical_match_score import AUTOLINK_MIN_SCORE

    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg4")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="XOCO",
            location_type="place",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = int(canon.id)  # type: ignore[arg-type]

        alias = StylebookLocationAlias(
            location_canonical_id=cid,
            alias_text="XOCO",
            normalized_alias="xoco",
            provenance="test",
            suppressed=False,
        )
        session.add(alias)
        session.commit()

        loc = SubstrateLocation(
            project_id=1,
            name="XOCO",
            normalized_name="xoco",
            location_type="address",
            identity_fingerprint="fp-type-gate-4",
        )

        ranked = rank_scored_canonical_recall_matches(
            session,
            location=loc,
            recall=[(cid, None)],
        )

    assert len(ranked) == 1
    _, _label, score, _ = ranked[0]
    assert score >= AUTOLINK_MIN_SCORE


def test_decide_canonical_persist_plan_type_gate_prevents_city_mismatch() -> None:
    """End-to-end: intersection substrate does not link to a city canonical."""
    from backfield_stylebook.canonical_policy import decide_canonical_persist_plan

    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg5")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            location_type="city",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = int(canon.id)  # type: ignore[arg-type]

        for alias_text, norm in [
            ("Chicago, IL", "chicago, il"),
            ("Illinois St. and Clark St., Chicago, IL", "illinois st. and clark st., chicago, il"),
        ]:
            session.add(StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text=alias_text,
                normalized_alias=norm,
                provenance="test",
                suppressed=False,
            ))
        session.commit()

        loc = SubstrateLocation(
            project_id=1,
            name="Illinois St. and Clark St., Chicago, IL",
            normalized_name="illinois st. and clark st., chicago, il",
            location_type="intersection_road",
            formatted_address="N Clark St and W Illinois St, Chicago, IL 60654",
            status="resolved",
            identity_fingerprint="fp-type-gate-5",
        )

        plan = decide_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            places_bucket="points",
            location=loc,
            entry={"address_place_kind": "public_named"},
        )

    assert plan.decision != CanonicalPersistDecision.LINK_EXISTING, (
        f"Intersection should not autolink to city canonical; got {plan.decision}"
    )
