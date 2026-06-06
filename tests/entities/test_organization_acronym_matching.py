"""Organization acronym ↔ expanded-name matching and type-aware disambiguation."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookOrganizationCanonical,
    SubstrateOrganization,
)
from backfield_entities.canonical.plan_types import CanonicalPersistDecision, CanonicalPersistPlan
from backfield_entities.entities.organization import (
    create_standalone_canonical,
    decide_organization_canonical_persist_plan,
    organization_acronym_from_name,
    organization_alias_lookup_keys,
    organization_substrate_alias_lookup_keys,
    organization_names_match_via_acronym,
    replan_organization_canonical_after_name_variants,
    retrieve_organization_canonical_candidates,
    seed_aliases_for_canonical_label,
    upsert_alias_for_canonical_text,
)
from backfield_entities.entities.organization.policy import ORGANIZATION_CANONICAL_TYPE_MISMATCH
from backfield_entities.entities.organization.types import (
    multiword_organization_names_share_ambiguous_acronym,
    organization_tier1_identity_compatible,
)
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-organization-acronym")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = Stylebook(organization_id=oid, slug="default", name="Default", is_default=True)
    session.add(sb)
    session.commit()
    session.refresh(sb)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    proj = BackfieldProject(name="Demo", slug="demo-org-acronym", organization_id=oid)
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return sb_id, int(proj.id)  # type: ignore[arg-type]


def test_organization_acronym_helpers() -> None:
    assert organization_acronym_from_name("Chicago Public Schools") == "cps"
    assert organization_acronym_from_name("National Basketball Association") == "nba"
    assert organization_acronym_from_name("NBA") is None
    assert organization_alias_lookup_keys("Chicago Public Schools") == (
        "chicago public schools",
        "cps",
    )
    assert organization_substrate_alias_lookup_keys("Chicago Public Schools") == (
        "chicago public schools",
    )
    assert organization_substrate_alias_lookup_keys("CPS") == ("cps",)
    assert organization_alias_lookup_keys("Cincinnati Reds") == ("cincinnati reds",)
    assert organization_names_match_via_acronym("nba", "national basketball association")
    assert not organization_names_match_via_acronym("colorado rockies", "cincinnati reds")
    assert multiword_organization_names_share_ambiguous_acronym(
        "colorado rockies",
        "cincinnati reds",
    )
    assert not organization_tier1_identity_compatible(
        substrate_norm="colorado rockies",
        canonical_label_norm="cincinnati reds",
    )


def test_recall_matches_expanded_substrate_to_acronym_canonical_label() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        create_standalone_canonical(
            session,
            stylebook_id=sb_id,
            label="NBA",
            organization_type="sports_league",
            provenance="test",
        )
        session.commit()
        organization = SubstrateOrganization(
            project_id=pid,
            name="National Basketball Association",
            normalized_name="national basketball association",
            organization_type="sports_league",
        )
        recall = retrieve_organization_canonical_candidates(
            session,
            stylebook_id=sb_id,
            organization=organization,
            limit=5,
        )
        assert recall
        assert recall[0][1] == "NBA"


def test_policy_links_cps_when_type_matches_school_district() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        canon = create_standalone_canonical(
            session,
            stylebook_id=sb_id,
            label="Chicago Public Schools",
            organization_type="school_district",
            provenance="test",
        )
        session.commit()
        organization = SubstrateOrganization(
            project_id=pid,
            name="CPS",
            normalized_name="cps",
            organization_type="school_district",
            identity_fingerprint="fp-cps-school",
        )
        session.add(organization)
        session.commit()
        plan = decide_organization_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            organization=organization,
        )
        assert plan.decision == CanonicalPersistDecision.LINK_EXISTING
        assert plan.existing_canonical_id == str(canon.id)


def test_policy_defers_cps_when_type_mismatches_child_protective() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        canon = create_standalone_canonical(
            session,
            stylebook_id=sb_id,
            label="Chicago Public Schools",
            organization_type="school_district",
            provenance="test",
        )
        session.commit()
        organization = SubstrateOrganization(
            project_id=pid,
            name="CPS",
            normalized_name="cps",
            organization_type="public_services",
            identity_fingerprint="fp-cps-child",
        )
        session.add(organization)
        session.commit()
        plan = decide_organization_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            organization=organization,
        )
        assert plan.decision == CanonicalPersistDecision.DEFER
        assert plan.resolution_reasons[0]["code"] == ORGANIZATION_CANONICAL_TYPE_MISMATCH
        assert plan.resolution_reasons[0]["canonical_id"] == str(canon.id)


def test_policy_picks_matching_cps_when_two_share_acronym_alias() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        school = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Chicago Public Schools",
            slug="chicago-public-schools",
            organization_type="school_district",
        )
        child = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Child Protective Services",
            slug="child-protective-services",
            organization_type="public_services",
        )
        session.add(school)
        session.add(child)
        session.flush()
        seed_aliases_for_canonical_label(
            session,
            canon_id=str(school.id),
            label="Chicago Public Schools",
            provenance="test",
        )
        seed_aliases_for_canonical_label(
            session,
            canon_id=str(child.id),
            label="Child Protective Services",
            provenance="test",
        )
        session.commit()
        organization = SubstrateOrganization(
            project_id=pid,
            name="CPS",
            normalized_name="cps",
            organization_type="school_district",
            identity_fingerprint="fp-cps-two",
        )
        session.add(organization)
        session.commit()
        plan = decide_organization_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            organization=organization,
        )
        assert plan.decision == CanonicalPersistDecision.LINK_EXISTING
        assert plan.existing_canonical_id == str(school.id)


def test_tier1_blocks_stale_full_name_alias_on_wrong_canonical() -> None:
    """A mistaken ``colorado rockies`` alias on a Cincinnati canonical must not auto-link."""
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        reds = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Cincinnati Reds",
            slug="cincinnati-reds",
            organization_type="sports_team",
        )
        session.add(reds)
        session.flush()
        seed_aliases_for_canonical_label(
            session,
            canon_id=str(reds.id),
            label="Cincinnati Reds",
            provenance="test",
        )
        upsert_alias_for_canonical_text(
            session,
            canon_id=str(reds.id),
            alias_text="Colorado Rockies",
            normalized_alias="colorado rockies",
            provenance="test_stale_alias",
        )
        session.commit()
        organization = SubstrateOrganization(
            project_id=pid,
            name="Colorado Rockies",
            normalized_name="colorado rockies",
            organization_type="sports_team",
            identity_fingerprint="fp-colorado-rockies-stale",
        )
        session.add(organization)
        session.commit()
        plan = decide_organization_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            organization=organization,
        )
        assert plan.decision != CanonicalPersistDecision.LINK_EXISTING
        assert plan.existing_canonical_id != str(reds.id)


def test_shared_derived_acronym_does_not_link_different_sports_teams() -> None:
    """Colorado Rockies and Cincinnati Reds both derive ``cr`` — must not auto-link."""
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        reds = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Cincinnati Reds",
            slug="cincinnati-reds",
            organization_type="sports_team",
        )
        session.add(reds)
        session.flush()
        seed_aliases_for_canonical_label(
            session,
            canon_id=str(reds.id),
            label="Cincinnati Reds",
            provenance="test",
        )
        session.commit()
        organization = SubstrateOrganization(
            project_id=pid,
            name="Colorado Rockies",
            normalized_name="colorado rockies",
            organization_type="sports_team",
            identity_fingerprint="fp-colorado-rockies",
        )
        session.add(organization)
        session.commit()
        plan = decide_organization_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            organization=organization,
        )
        assert plan.decision != CanonicalPersistDecision.LINK_EXISTING
        assert plan.existing_canonical_id != str(reds.id)


def test_replan_links_via_variant_expanded_name() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        canon = create_standalone_canonical(
            session,
            stylebook_id=sb_id,
            label="Chicago Public Schools",
            organization_type="school_district",
            provenance="test",
        )
        session.commit()
        organization = SubstrateOrganization(
            project_id=pid,
            name="CPS",
            normalized_name="cps",
            organization_type="school_district",
            identity_fingerprint="fp-cps-variant",
        )
        session.add(organization)
        session.commit()
        initial = CanonicalPersistPlan(
            decision=CanonicalPersistDecision.MATERIALIZE_NEW,
            resolution_reasons=({"code": "materialized_new_canonical"},),
        )
        out = replan_organization_canonical_after_name_variants(
            session,
            stylebook_id=sb_id,
            organization=organization,
            variant_names=("Chicago Public Schools",),
        )
        assert out.decision == CanonicalPersistDecision.LINK_EXISTING
        assert out.existing_canonical_id == str(canon.id)
        assert any(
            isinstance(r, dict) and r.get("code") == "organization_name_variant_recall"
            for r in out.resolution_reasons
        )
        _ = initial
