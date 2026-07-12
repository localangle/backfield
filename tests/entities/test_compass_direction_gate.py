"""Compass-direction conflict gate blocks east/west (and north/south) fuzzy autolinks."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_entities.canonical.match_score import (
    AUTOLINK_MIN_SCORE,
    RECALL_MIN_SCORE,
    CanonicalMatchFeatures,
    SubstrateMatchInput,
    classify_recall_score,
    policy_match_score,
)
from backfield_entities.canonical.plan_types import CanonicalPersistDecision
from backfield_entities.entities.location.policy import (
    _apply_recall_match_gates,
    _compass_axes_conflict,
    _compass_axes_from_head,
    _compass_direction_conflict,
    decide_location_canonical_persist_plan,
    rank_scored_canonical_recall_matches,
)
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_stylebook(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-compass-gate")
    session.add(org)
    session.commit()
    session.refresh(org)
    sb = Stylebook(
        organization_id=int(org.id),  # type: ignore[arg-type]
        slug="default",
        name="Default",
        is_default=True,
    )
    session.add(sb)
    proj = BackfieldProject(name="Demo", slug="demo-compass", organization_id=int(org.id))  # type: ignore[arg-type]
    session.add(proj)
    session.commit()
    session.refresh(sb)
    session.refresh(proj)
    return int(sb.id), int(proj.id)  # type: ignore[arg-type]


def test_compass_axes_from_head() -> None:
    assert _compass_axes_from_head("East Coast, US") == frozenset({"east"})
    assert _compass_axes_from_head("West Coast, US") == frozenset({"west"})
    assert _compass_axes_from_head("Northeast, US") == frozenset({"north", "east"})
    assert _compass_axes_from_head("Northwest Region") == frozenset({"north", "west"})
    assert _compass_axes_from_head("Midwest, US") == frozenset()


def test_compass_axes_conflict_opposing_pairs() -> None:
    assert _compass_axes_conflict(frozenset({"east"}), frozenset({"west"}))
    assert _compass_axes_conflict(frozenset({"north"}), frozenset({"south"}))
    assert not _compass_axes_conflict(frozenset({"east"}), frozenset({"east"}))
    assert not _compass_axes_conflict(frozenset({"north", "east"}), frozenset({"north", "east"}))


def test_raw_score_autolinks_east_west_coast_but_gate_demotes() -> None:
    sub = SubstrateMatchInput(
        name="West Coast, US",
        normalized_name="west coast, us",
    )
    feat = CanonicalMatchFeatures(
        canonical_id="1",
        label="East Coast, US",
        normalized_aliases=("east coast, us",),
    )
    raw = policy_match_score(sub, feat, substrate_location_type="region_national")
    assert raw >= AUTOLINK_MIN_SCORE
    assert classify_recall_score(raw) == "autolink"
    assert _compass_direction_conflict("West Coast, US", feat)

    loc = SubstrateLocation(
        project_id=1,
        name="West Coast, US",
        normalized_name="west coast, us",
        location_type="region_national",
        status="resolved",
        identity_fingerprint="fp-compass-1",
    )
    canon = StylebookLocationCanonical(
        stylebook_id=1,
        label="East Coast, US",
        slug="east-coast-us",
        location_type="region_national",
        status="active",
    )
    gated = _apply_recall_match_gates(
        raw,
        location=loc,
        canon=canon,
        feat=feat,
        comps={},
    )
    assert gated < RECALL_MIN_SCORE
    assert classify_recall_score(gated) == "below_recall"


def test_same_compass_direction_still_autolinks() -> None:
    sub = SubstrateMatchInput(
        name="East Coast, US",
        normalized_name="east coast, us",
    )
    feat = CanonicalMatchFeatures(
        canonical_id="1",
        label="East Coast, US",
        normalized_aliases=("east coast, us",),
    )
    raw = policy_match_score(sub, feat, substrate_location_type="region_national")
    assert raw >= AUTOLINK_MIN_SCORE
    assert not _compass_direction_conflict("East Coast, US", feat)

    loc = SubstrateLocation(
        project_id=1,
        name="East Coast, US",
        normalized_name="east coast, us",
        location_type="region_national",
        status="resolved",
        identity_fingerprint="fp-compass-2",
    )
    canon = StylebookLocationCanonical(
        stylebook_id=1,
        label="East Coast, US",
        slug="east-coast-us",
        location_type="region_national",
        status="active",
    )
    gated = _apply_recall_match_gates(
        raw,
        location=loc,
        canon=canon,
        feat=feat,
        comps={},
    )
    assert gated >= AUTOLINK_MIN_SCORE


def test_west_coast_does_not_fuzzy_autolink_east_coast_canonical() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="East Coast, US",
            slug="east-coast-us",
            location_type="region_national",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        cid = str(canon.id)

        loc = SubstrateLocation(
            project_id=pid,
            name="West Coast, US",
            normalized_name="west coast, us",
            location_type="region_national",
            status="resolved",
            identity_fingerprint="fp-compass-3",
        )

        ranked = rank_scored_canonical_recall_matches(
            session,
            location=loc,
            recall=[(cid, None)],
        )
        assert ranked
        _cid, _label, gated_score, _idx, _raw = ranked[0]
        assert gated_score < AUTOLINK_MIN_SCORE

        plan = decide_location_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            places_bucket="ready",
            location=loc,
            entry={},
        )

    assert plan.decision == CanonicalPersistDecision.MATERIALIZE_NEW
    assert plan.existing_canonical_id is None
