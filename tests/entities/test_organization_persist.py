"""Tests for Stylebook organization canonical persist and link helpers."""

from __future__ import annotations

from uuid import UUID

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    SubstrateOrganization,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED, CANONICAL_LINK_PENDING
from backfield_entities.canonical.plan_types import CanonicalPersistDecision
from backfield_entities.entities.organization import (
    allocate_unique_organization_canonical_slug,
    create_standalone_canonical,
    decide_organization_canonical_persist_plan,
    link_substrate_to_canonical_atomic,
    link_to_existing_canonical,
    materialize_new_canonical_and_link,
    organization_identity_fingerprint,
    rank_canonical_suggestions_for_substrate,
    upsert_alias_for_canonical_text,
)
from sqlmodel import Session, SQLModel, create_engine, select


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_stylebook(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-organization-persist")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = Stylebook(organization_id=oid, slug="default", name="Default", is_default=True)
    session.add(sb)
    session.commit()
    session.refresh(sb)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    proj = BackfieldProject(name="Demo", slug="demo-org", organization_id=oid)
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return sb_id, int(proj.id)  # type: ignore[arg-type]


def test_allocate_unique_organization_canonical_slug_suffixes_on_collision() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, _pid = _seed_stylebook(session)
        slug = allocate_unique_organization_canonical_slug(
            session,
            stylebook_id=sb_id,
            label="Chicago Police Department",
        )
        assert slug == "chicago-police-department"
        session.add(
            StylebookOrganizationCanonical(
                stylebook_id=sb_id,
                label="Chicago Police Department",
                slug="chicago-police-department",
            )
        )
        session.commit()
        assert (
            allocate_unique_organization_canonical_slug(
                session,
                stylebook_id=sb_id,
                label="Chicago Police Department",
            )
            == "chicago-police-department-2"
        )


def test_create_standalone_canonical_creates_uuid_and_alias() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, _pid = _seed_stylebook(session)
        canon = create_standalone_canonical(
            session,
            stylebook_id=sb_id,
            label="Chicago Teachers Union",
            organization_type="community_group",
        )
        session.commit()
        UUID(canon.id)
        assert canon.organization_type == "community_group"
        aliases = session.exec(
            select(StylebookOrganizationAlias).where(
                StylebookOrganizationAlias.organization_canonical_id == str(canon.id)
            )
        ).all()
        assert len(aliases) == 1
        assert aliases[0].normalized_alias == "chicago teachers union"


def test_materialize_new_canonical_and_link_mirrors_type() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        organization = SubstrateOrganization(
            project_id=pid,
            name="Lincoln Park High School",
            normalized_name="lincoln park high school",
            organization_type="school",
            identity_fingerprint=organization_identity_fingerprint(
                normalized_name="lincoln park high school",
                organization_type="school",
            ),
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        session.add(organization)
        session.commit()
        session.refresh(organization)

        materialize_new_canonical_and_link(session, stylebook_id=sb_id, organization=organization)
        session.commit()
        session.refresh(organization)

        assert organization.stylebook_organization_canonical_id is not None
        assert organization.canonical_link_status == CANONICAL_LINK_LINKED
        canon = session.get(
            StylebookOrganizationCanonical,
            str(organization.stylebook_organization_canonical_id),
        )
        assert canon is not None
        assert canon.label == "Lincoln Park High School"
        assert canon.organization_type == "school"


def test_decide_organization_links_exact_name_and_type() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Chicago Police Department",
            slug="chicago-police-department",
            organization_type="law_enforcement",
        )
        session.add(canon)
        session.commit()
        organization = SubstrateOrganization(
            project_id=pid,
            name="Chicago Police Department",
            normalized_name="chicago police department",
            organization_type="law_enforcement",
        )
        session.add(organization)
        session.commit()
        session.refresh(organization)

        plan = decide_organization_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            organization=organization,
        )
        assert plan.decision == CanonicalPersistDecision.LINK_EXISTING
        assert plan.existing_canonical_id == str(canon.id)


def test_decide_organization_defers_when_type_differs_on_alias() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Chicago",
            slug="chicago",
            organization_type="government",
        )
        session.add(canon)
        session.flush()
        upsert_alias_for_canonical_text(
            session,
            canon_id=str(canon.id),
            alias_text="Chicago",
            normalized_alias="chicago",
            provenance="seed",
        )
        organization = SubstrateOrganization(
            project_id=pid,
            name="Chicago",
            normalized_name="chicago",
            organization_type="sports_team",
        )
        session.add(organization)
        session.commit()
        session.refresh(organization)

        plan = decide_organization_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            organization=organization,
        )
        assert plan.decision == CanonicalPersistDecision.DEFER
        codes = [str(r.get("code")) for r in plan.resolution_reasons if isinstance(r, dict)]
        assert "organization_canonical_type_mismatch" in codes


def test_decide_organization_defers_on_ambiguous_strong_matches() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        for i, slug in enumerate(("union-a", "union-b")):
            session.add(
                StylebookOrganizationCanonical(
                    stylebook_id=sb_id,
                    label="Chicago Teachers Union",
                    slug=slug,
                    organization_type="community_group",
                )
            )
        session.commit()
        organization = SubstrateOrganization(
            project_id=pid,
            name="Chicago Teachers Union",
            normalized_name="chicago teachers union",
            organization_type="community_group",
        )
        session.add(organization)
        session.commit()
        session.refresh(organization)

        plan = decide_organization_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            organization=organization,
        )
        assert plan.decision == CanonicalPersistDecision.DEFER
        codes = [str(r.get("code")) for r in plan.resolution_reasons if isinstance(r, dict)]
        assert "ambiguous_organization_canonical_match" in codes


def test_decide_organization_materializes_when_no_match() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        organization = SubstrateOrganization(
            project_id=pid,
            name="New Agency",
            normalized_name="new agency",
            organization_type="government",
        )
        session.add(organization)
        session.commit()
        session.refresh(organization)

        plan = decide_organization_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            organization=organization,
        )
        assert plan.decision == CanonicalPersistDecision.MATERIALIZE_NEW


def test_rank_canonical_suggestions_prefers_exact_alias() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Chicago City Council",
            slug="chicago-city-council",
            organization_type="legislative_body",
        )
        session.add(canon)
        session.flush()
        upsert_alias_for_canonical_text(
            session,
            canon_id=str(canon.id),
            alias_text="Chicago City Council",
            normalized_alias="chicago city council",
            provenance="seed",
        )
        organization = SubstrateOrganization(
            project_id=pid,
            name="Chicago City Council",
            normalized_name="chicago city council",
            organization_type="legislative_body",
        )
        session.add(organization)
        session.commit()
        session.refresh(organization)

        suggestions = rank_canonical_suggestions_for_substrate(
            session,
            stylebook_id=sb_id,
            organization=organization,
        )
        assert suggestions
        assert suggestions[0][0] == str(canon.id)


def test_link_substrate_to_canonical_atomic_is_idempotent() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Chicago Teachers Union",
            slug="chicago-teachers-union",
            organization_type="community_group",
        )
        session.add(canon)
        session.commit()
        organization = SubstrateOrganization(
            project_id=pid,
            name="Chicago Teachers Union",
            normalized_name="chicago teachers union",
            organization_type="community_group",
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        session.add(organization)
        session.commit()
        session.refresh(organization)

        changed = link_substrate_to_canonical_atomic(
            session,
            stylebook_id=sb_id,
            organization=organization,
            target_canonical_id=str(canon.id),
        )
        assert changed is True
        session.commit()
        session.refresh(organization)
        assert organization.stylebook_organization_canonical_id == str(canon.id)

        changed_again = link_substrate_to_canonical_atomic(
            session,
            stylebook_id=sb_id,
            organization=organization,
            target_canonical_id=str(canon.id),
        )
        assert changed_again is False


def test_link_to_existing_canonical_records_alias_when_name_differs() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="Chicago Police Department",
            slug="chicago-police-department",
            organization_type="law_enforcement",
        )
        session.add(canon)
        session.flush()
        upsert_alias_for_canonical_text(
            session,
            canon_id=str(canon.id),
            alias_text="Chicago Police Department",
            normalized_alias="chicago police department",
            provenance="seed",
        )
        organization = SubstrateOrganization(
            project_id=pid,
            name="CPD",
            normalized_name="cpd",
            organization_type="law_enforcement",
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        session.add(organization)
        session.commit()
        session.refresh(organization)

        link_to_existing_canonical(
            session,
            stylebook_id=sb_id,
            organization=organization,
            canonical_id=str(canon.id),
        )
        session.commit()

        aliases = session.exec(
            select(StylebookOrganizationAlias).where(
                StylebookOrganizationAlias.organization_canonical_id == str(canon.id)
            )
        ).all()
        norms = {a.normalized_alias for a in aliases}
        assert "cpd" in norms
