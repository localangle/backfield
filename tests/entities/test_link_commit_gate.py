"""Sync link commit gate and trusted-alias quarantine."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    StylebookPersonAlias,
    StylebookPersonCanonical,
    SubstrateOrganization,
    SubstratePerson,
)
from backfield_entities.canonical.link_commit_gate import (
    VETO_OBVIOUS_NAME_MISMATCH,
    coerce_blocked_link_plan,
    sync_link_commit_blocked,
)
from backfield_entities.canonical.plan_types import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from backfield_entities.entities.organization.recall import (
    canonical_ids_from_organization_name_keys,
)
from backfield_entities.entities.person.recall import canonical_ids_from_person_name_keys
from backfield_entities.entities.person.types import normalize_person_text
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_stylebook(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-link-commit-gate")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = Stylebook(
        organization_id=oid,
        slug="default",
        name="Default",
        is_default=True,
    )
    session.add(sb)
    session.commit()
    session.refresh(sb)
    proj = BackfieldProject(name="Demo", slug="demo-link-commit-gate", organization_id=oid)
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return int(sb.id), int(proj.id)  # type: ignore[arg-type]


def test_sync_gate_blocks_kam_jones_to_tre_jones() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, project_id = _seed_stylebook(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Tre Jones",
            slug="tre-jones",
        )
        session.add(canon)
        session.flush()
        person = SubstratePerson(
            project_id=project_id,
            name="Kam Jones",
            normalized_name=normalize_person_text("Kam Jones"),
            canonical_link_status="pending",
        )
        session.add(person)
        session.commit()
        assert canon.id is not None

        veto = sync_link_commit_blocked(
            session,
            entity_type="person",
            substrate_row=person,
            canonical_id=str(canon.id),
            stylebook_id=sb_id,
        )
        assert veto == VETO_OBVIOUS_NAME_MISMATCH

        coerced = coerce_blocked_link_plan(
            CanonicalPersistPlan(
                decision=CanonicalPersistDecision.LINK_EXISTING,
                existing_canonical_id=str(canon.id),
            ),
            entity_type="person",
            substrate_row=person,
            veto_code=veto,
        )
        assert coerced.decision == CanonicalPersistDecision.MATERIALIZE_NEW
        assert any(
            isinstance(r, dict) and r.get("code") == "sync_link_commit_veto"
            for r in coerced.resolution_reasons
        )


def test_sync_gate_blocks_university_of_maryland_to_umn_duluth() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, project_id = _seed_stylebook(session)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="University of Minnesota Duluth",
            slug="university-of-minnesota-duluth",
            organization_type="school",
        )
        session.add(canon)
        session.flush()
        org = SubstrateOrganization(
            project_id=project_id,
            name="University of Maryland",
            normalized_name="university of maryland",
            organization_type="school",
            canonical_link_status="pending",
        )
        session.add(org)
        session.commit()
        assert canon.id is not None

        veto = sync_link_commit_blocked(
            session,
            entity_type="organization",
            substrate_row=org,
            canonical_id=str(canon.id),
            stylebook_id=sb_id,
        )
        assert veto == VETO_OBVIOUS_NAME_MISMATCH


def test_trusted_alias_only_excludes_substrate_ingest_person_alias() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, _project_id = _seed_stylebook(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Tre Jones",
            slug="tre-jones-alias",
        )
        session.add(canon)
        session.flush()
        assert canon.id is not None
        session.add(
            StylebookPersonAlias(
                person_canonical_id=str(canon.id),
                alias_text="Kam Jones",
                normalized_alias=normalize_person_text("Kam Jones"),
                provenance="substrate_ingest",
                suppressed=False,
            )
        )
        session.commit()

        untrusted = canonical_ids_from_person_name_keys(
            session,
            stylebook_id=sb_id,
            name_or_norm="Kam Jones",
            trusted_alias_only=False,
        )
        trusted = canonical_ids_from_person_name_keys(
            session,
            stylebook_id=sb_id,
            name_or_norm="Kam Jones",
            trusted_alias_only=True,
        )
        assert untrusted == [str(canon.id)]
        assert trusted == []


def test_trusted_alias_only_keeps_editorial_organization_alias() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, _project_id = _seed_stylebook(session)
        canon = StylebookOrganizationCanonical(
            stylebook_id=sb_id,
            label="University of Minnesota Duluth",
            slug="umd-editorial",
            organization_type="school",
        )
        session.add(canon)
        session.flush()
        assert canon.id is not None
        session.add(
            StylebookOrganizationAlias(
                organization_canonical_id=str(canon.id),
                alias_text="UMD",
                normalized_alias="umd",
                provenance="stylebook_ui_accept",
                suppressed=False,
            )
        )
        session.commit()

        trusted = canonical_ids_from_organization_name_keys(
            session,
            stylebook_id=sb_id,
            name_or_norm="UMD",
            trusted_alias_only=True,
        )
        assert trusted == [str(canon.id)]
