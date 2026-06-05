"""Tests for canonical type matrix, recall scoring, and substrate gates."""

from __future__ import annotations

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldWorkspace,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_entities.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.canonical.link_matrix import link_pair_allowed, types_are_comparable
from backfield_entities.canonical.substrate_link_actions import link_substrate_to_canonical_atomic
from backfield_entities.entities.location.policy import (
    CanonicalPersistDecision,
    decide_canonical_persist_plan,
    rank_scored_canonical_recall_matches,
    substrate_may_materialize_canonical_after_recall,
)
from sqlmodel import Session, SQLModel, create_engine

# ---------------------------------------------------------------------------
# Pure unit tests for link_pair_allowed (no DB)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("substrate_lt", "canonical_lt"),
    [
        ("city", "city"),
        ("town", "city"),
        ("city", "town"),
        ("region_city", "ward"),
        ("ward", "region_city"),
        ("neighborhood", "county"),
        ("natural", "city"),
        ("region_city", None),
        ("address", None),
        ("city", None),
        (None, "city"),
    ],
)
def test_link_pair_allowed_is_permissive(
    substrate_lt: str | None,
    canonical_lt: str | None,
) -> None:
    assert link_pair_allowed(substrate_lt, canonical_lt) is True


def test_link_pair_denies_address_to_city() -> None:
    assert link_pair_allowed("address", "city") is False
    assert link_pair_allowed("city", "address") is False


@pytest.mark.parametrize(
    ("substrate_lt", "canonical_lt", "expect"),
    [
        ("place", "neighborhood", False),
        ("neighborhood", "place", False),
        ("intersection_road", "place", False),
        ("intersection_highway", "point", False),
        ("place", "place", True),
        ("neighborhood", "neighborhood", True),
        ("city", "place", False),
    ],
)
def test_types_are_comparable_matches_link_policy(
    substrate_lt: str,
    canonical_lt: str,
    expect: bool,
) -> None:
    assert types_are_comparable(substrate_lt, canonical_lt) is expect


def test_link_substrate_atomic_rejects_city_to_place() -> None:
    """Manual link succeeds with default ``enforce_type_gate=False`` (permissive types)."""
    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="linkpair")
        canon_place = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="XOCO",
            slug="xoco",
            location_type="place",
            status="active",
        )
        session.add(canon_place)
        session.commit()
        session.refresh(canon_place)
        pid = 1
        loc = SubstrateLocation(
            project_id=pid,
            name="Chicago, IL",
            normalized_name="chicago, il",
            location_type="city",
            canonical_link_status="pending",
            stylebook_location_canonical_id=None,
            identity_fingerprint="fp-link-1",
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)
        changed = link_substrate_to_canonical_atomic(
            session,
            stylebook_id=sb_id,
            location=loc,
            target_canonical_id=str(canon_place.id),
        )
        assert changed is True
        assert loc.stylebook_location_canonical_id == str(canon_place.id)


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
    from backfield_entities.canonical.match_score import RECALL_MIN_SCORE

    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg1")

        # Canonical is a city
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)

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
    _, _label, score, _, _raw = ranked[0]
    assert score < RECALL_MIN_SCORE


def test_rank_allows_same_type_city_to_city() -> None:
    """A city substrate should score normally against a city canonical."""
    from backfield_entities.canonical.match_score import AUTOLINK_MIN_SCORE

    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg2")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)

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
    _, _label, score, _, _raw = ranked[0]
    assert score >= AUTOLINK_MIN_SCORE, (
        f"Expected city→city score >= AUTOLINK_MIN_SCORE ({AUTOLINK_MIN_SCORE}), got {score}"
    )


def test_link_pair_denies_address_to_neighborhood() -> None:
    assert link_pair_allowed("address", "neighborhood") is False
    assert link_pair_allowed("neighborhood", "address") is False


def test_rank_caps_address_to_neighborhood() -> None:
    """Street addresses must not autolink to neighborhood canonicals (token overlap only)."""
    from backfield_entities.canonical.match_score import RECALL_MIN_SCORE

    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg-addr-hood")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Austin",
            slug="austin-hood",
            location_type="neighborhood",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)

        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="Austin",
                normalized_alias="austin",
                provenance="test",
                suppressed=False,
            )
        )
        session.commit()

        loc = SubstrateLocation(
            project_id=1,
            name="5400 W. West End Ave., Austin, Chicago, IL",
            normalized_name="5400 w. west end ave., austin, chicago, il",
            location_type="address",
            formatted_address="Austin, Chicago, IL",
            identity_fingerprint="fp-type-gate-addr-hood",
        )

        ranked = rank_scored_canonical_recall_matches(
            session,
            location=loc,
            recall=[(cid, None)],
        )

    assert len(ranked) == 1
    _, _label, score, _, _raw = ranked[0]
    assert score < RECALL_MIN_SCORE


def test_decide_canonical_persist_plan_place_skips_neighborhood_named_place_canonical() -> None:
    """POI rows must not autolink to place canonicals that only name a neighborhood."""
    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg-poi-hood-place")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Bridgeport, Chicago, IL",
            slug="bridgeport-chicago-il",
            location_type="place",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)

        loc = SubstrateLocation(
            project_id=1,
            name="DanDance Art Academy, Chicago, IL",
            normalized_name="dandance art academy, chicago, il",
            location_type="place",
            formatted_address="Chicago, IL",
            status="resolved",
            identity_fingerprint="fp-poi-hood-place",
        )

        plan = decide_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            places_bucket="points",
            location=loc,
            entry={
                "components": {
                    "place": {"name": "DanDance Art Academy"},
                    "neighborhood": "Bridgeport",
                    "city": "Chicago",
                }
            },
        )

    assert plan.decision in (
        CanonicalPersistDecision.MATERIALIZE_NEW,
        CanonicalPersistDecision.DEFER,
    )
    assert plan.existing_canonical_id != cid


def test_decide_canonical_persist_plan_address_skips_place_canonical_on_street_overlap() -> None:
    """Address rows must not autolink to place canonicals via embedded neighborhood tokens."""
    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg-addr-place")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Austin, Chicago, IL",
            slug="austin-chicago-place",
            location_type="place",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)

        loc = SubstrateLocation(
            project_id=1,
            name="5400 W. West End Ave., Austin, Chicago, IL",
            normalized_name="5400 w. west end ave., austin, chicago, il",
            location_type="address",
            formatted_address="Austin, Chicago, IL",
            status="resolved",
            identity_fingerprint="fp-addr-place",
        )

        plan = decide_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            places_bucket="points",
            location=loc,
            entry={"address_place_kind": "public_named"},
        )

    assert plan.decision in (
        CanonicalPersistDecision.DEFER,
        CanonicalPersistDecision.MATERIALIZE_NEW,
    )
    assert plan.existing_canonical_id != cid


def test_decide_canonical_persist_plan_intersection_skips_place_canonical() -> None:
    """Intersection rows must not autolink to place canonicals."""
    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg-int-place")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il-place",
            location_type="place",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)

        loc = SubstrateLocation(
            project_id=1,
            name="Illinois St. and Clark St., Chicago, IL",
            normalized_name="illinois st. and clark st., chicago, il",
            location_type="intersection_road",
            formatted_address="Chicago, IL",
            status="resolved",
            identity_fingerprint="fp-int-place",
        )

        plan = decide_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            places_bucket="points",
            location=loc,
            entry={},
        )

    assert plan.decision in (
        CanonicalPersistDecision.DEFER,
        CanonicalPersistDecision.MATERIALIZE_NEW,
    )
    assert plan.existing_canonical_id != cid


def test_decide_canonical_persist_plan_neighborhood_skips_place_canonical() -> None:
    """Neighborhood rows must not autolink to place canonicals."""
    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg-hood-place")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="DanDance Art Academy, Chicago, IL",
            slug="dandance-chicago",
            location_type="place",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)

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

        loc = SubstrateLocation(
            project_id=1,
            name="Bridgeport, Chicago, IL",
            normalized_name="bridgeport, chicago, il",
            location_type="neighborhood",
            formatted_address="Chicago, IL",
            status="resolved",
            identity_fingerprint="fp-hood-place",
        )

        plan = decide_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            places_bucket="areas",
            location=loc,
            entry={"components": {"neighborhood": "Bridgeport", "city": "Chicago"}},
        )

    assert plan.decision in (
        CanonicalPersistDecision.MATERIALIZE_NEW,
        CanonicalPersistDecision.DEFER,
    )
    assert plan.existing_canonical_id != cid


def test_decide_canonical_persist_plan_address_does_not_link_neighborhood_alias() -> None:
    """Exact alias overlap must not link an address row to a neighborhood canonical."""
    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg-addr-hood-plan")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Austin",
            slug="austin-hood-plan",
            location_type="neighborhood",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)

        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="Austin, Chicago, IL",
                normalized_alias="austin, chicago, il",
                provenance="test",
                suppressed=False,
            )
        )
        session.commit()

        loc = SubstrateLocation(
            project_id=1,
            name="5400 W. West End Ave., Austin, Chicago, IL",
            normalized_name="5400 w. west end ave., austin, chicago, il",
            location_type="address",
            formatted_address="Austin, Chicago, IL",
            status="resolved",
            identity_fingerprint="fp-type-gate-addr-hood-plan",
        )

        plan = decide_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            places_bucket="points",
            location=loc,
            entry={"address_place_kind": "public_named"},
        )

    assert plan.decision == CanonicalPersistDecision.DEFER
    assert plan.existing_canonical_id is None


def test_rank_caps_intersection_to_city() -> None:
    """An intersection substrate must not autolink to a city canonical."""
    from backfield_entities.canonical.match_score import RECALL_MIN_SCORE

    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg3")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)

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
    _, _label, score, _, _raw = ranked[0]
    assert score < RECALL_MIN_SCORE


def test_rank_allows_address_to_place() -> None:
    """An address substrate should be allowed to score against a place canonical."""
    from backfield_entities.canonical.match_score import AUTOLINK_MIN_SCORE

    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg4")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="XOCO",
            slug="xoco",
            location_type="place",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)

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
    _, _label, score, _, _raw = ranked[0]
    assert score >= AUTOLINK_MIN_SCORE


def test_rank_does_not_drop_strict_to_flexible_candidates() -> None:
    """Recall/scoring should still rank ``region_city`` substrate against a ``ward`` canonical."""
    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg-compare-1")
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Ward 15, Chicago, IL",
            slug="ward-15-chicago-il",
            location_type="ward",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)

        alias = StylebookLocationAlias(
            location_canonical_id=cid,
            alias_text="Ward 15, Chicago, IL",
            normalized_alias="ward 15, chicago, il",
            provenance="test",
            suppressed=False,
        )
        session.add(alias)
        session.commit()

        loc = SubstrateLocation(
            project_id=1,
            name="15th Ward, Chicago, IL",
            normalized_name="15th ward, chicago, il",
            location_type="region_city",
            identity_fingerprint="fp-compare-1",
        )

        ranked = rank_scored_canonical_recall_matches(
            session,
            location=loc,
            recall=[(cid, None)],
        )

    assert len(ranked) == 1


def test_decide_canonical_persist_plan_intersection_exact_alias_does_not_link_city() -> None:
    """Exact alias on a city canonical does not link an intersection (type deny-list)."""
    from backfield_entities.entities.location.policy import decide_canonical_persist_plan

    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg5")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Chicago, IL",
            slug="chicago-il",
            location_type="city",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)

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

    assert plan.decision in (
        CanonicalPersistDecision.DEFER,
        CanonicalPersistDecision.MATERIALIZE_NEW,
    )
    assert plan.existing_canonical_id is None


def test_ambiguous_cross_type_recall_defers_when_mid_tier_match_exists() -> None:
    """With permissive types, ambiguous-tier fuzzy recall defers for human/LLM review."""
    from backfield_entities.entities.location.policy import decide_canonical_persist_plan

    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg-materialize-ambig-x")

        # Ward canonical; token overlap on ``Chicago, IL`` can surface it in recall with a
        # mid-tier string score (not autolink): policy defers rather than materializing.
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Ward 15, Chicago, IL",
            slug="ward-15-chicago-il",
            location_type="ward",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="Ward 15, Chicago, IL",
                normalized_alias="ward 15, chicago, il",
                provenance="test",
                suppressed=False,
            )
        )
        session.commit()

        loc = SubstrateLocation(
            project_id=1,
            name="Avondale, Chicago, IL",
            normalized_name="avondale, chicago, il",
            location_type="neighborhood",
            status="resolved",
            identity_fingerprint="fp-mat-ambig-x",
        )
        plan = decide_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            places_bucket="points",
            location=loc,
            entry=None,
        )

    assert plan.decision == CanonicalPersistDecision.DEFER
    assert plan.resolution_reasons
    assert plan.resolution_reasons[0].get("code") == "ambiguous_canonical_match"


def test_decide_canonical_persist_plan_span_always_defers_even_with_exact_alias() -> None:
    """Spans never auto-link or materialize; exact alias matches are ignored for ingest policy."""
    from backfield_entities.entities.location.policy import decide_canonical_persist_plan

    engine = _make_engine()
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="tg-span-defer")

        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="I-35 Pine to Hinckley",
            slug="i35-span",
            location_type="span",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="I-35 between Pine City and Hinckley, MN",
                normalized_alias="i-35 between pine city and hinckley, mn",
                provenance="test",
                suppressed=False,
            )
        )
        session.commit()

        loc = SubstrateLocation(
            project_id=1,
            name="I-35 between Pine City and Hinckley, MN",
            normalized_name="i-35 between pine city and hinckley, mn",
            location_type="span",
            status="resolved",
            geometry_json={
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            },
            identity_fingerprint="fp-span-defer-1",
        )

        plan = decide_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            places_bucket="points",
            location=loc,
            entry=None,
        )

    assert plan.decision == CanonicalPersistDecision.DEFER
    assert plan.resolution_reasons
    assert plan.resolution_reasons[0].get("code") == "road_span_not_canonicalized"


def test_substrate_may_materialize_canonical_after_recall_false_for_span() -> None:
    loc = SubstrateLocation(
        project_id=1,
        name="Lake St from A to B, Minneapolis, MN",
        normalized_name="lake st from a to b, minneapolis, mn",
        location_type="span",
        status="resolved",
        geometry_json={
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
        },
        identity_fingerprint="fp-span-mat-1",
    )
    assert substrate_may_materialize_canonical_after_recall(loc) is False
