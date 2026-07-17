"""Person canonical recall (alias-first, capped candidates)."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookPersonCanonical,
    SubstratePerson,
)
from backfield_entities.canonical.plan_types import CanonicalPersistDecision
from backfield_entities.entities.person.persist import upsert_alias_for_canonical_text
from backfield_entities.entities.person.policy import (
    decide_person_canonical_persist_plan,
    find_existing_person_canonical_id_by_strong_identity,
    person_strong_identity_matches_canonical,
)
from backfield_entities.entities.person.recall import (
    PERSON_RECALL_DEFAULT_LIMIT,
    retrieve_person_canonical_candidates,
)
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-person-recall")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = Stylebook(organization_id=oid, slug="default", name="Default", is_default=True)
    session.add(sb)
    session.commit()
    session.refresh(sb)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    proj = BackfieldProject(name="Demo", slug="demo-recall", organization_id=oid)
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return sb_id, int(proj.id)  # type: ignore[arg-type]


def test_person_strong_identity_requires_canonical_label_name_match() -> None:
    """Same affiliation must not tier-1 link when display names differ (Faith vs Keith)."""
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Faith Hernandez",
            slug="faith-hernandez",
            title="Resident",
            affiliation="Chicago Housing Authority",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        for name, title in (
            ("Keith Pettigrew", "CEO"),
            ("Matthew Aguilar", "Spokesperson"),
        ):
            person = SubstratePerson(
                project_id=pid,
                name=name,
                normalized_name=name.lower(),
                title=title,
                affiliation="Chicago Housing Authority",
            )
            assert not person_strong_identity_matches_canonical(person, canon)


def test_person_strong_identity_ignores_title() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Jane Doe",
            slug="jane-doe",
            title="Mayor",
            affiliation="City of Chicago",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        person = SubstratePerson(
            project_id=pid,
            name="Jane Doe",
            normalized_name="jane doe",
            title="Resident",
            affiliation="City of Chicago",
        )
        assert person_strong_identity_matches_canonical(person, canon)


def test_strong_identity_ignores_inactive_duplicate_canonical() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        active = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Jane Doe",
            slug="active-jane-doe",
            affiliation="City of Chicago",
            status="active",
        )
        inactive = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Jane Doe",
            slug="inactive-jane-doe",
            affiliation="City of Chicago",
            status="inactive",
        )
        session.add_all((active, inactive))
        session.commit()
        person = SubstratePerson(
            project_id=pid,
            name="Jane Doe",
            normalized_name="jane doe",
            affiliation="City of Chicago",
        )

        assert find_existing_person_canonical_id_by_strong_identity(
            session,
            stylebook_id=sb_id,
            person=person,
        ) == str(active.id)


def test_recall_caps_at_default_limit() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        for i in range(30):
            session.add(
                StylebookPersonCanonical(
                    stylebook_id=sb_id,
                    label=f"Alex Smith {i}",
                    slug=f"alex-smith-{i}",
                    affiliation="Org",
                )
            )
        session.commit()
        person = SubstratePerson(
            project_id=pid,
            name="Alex Smith",
            normalized_name="alex smith",
            affiliation="Org",
        )
        recall = retrieve_person_canonical_candidates(
            session, stylebook_id=sb_id, person=person
        )
        assert len(recall) <= PERSON_RECALL_DEFAULT_LIMIT
        assert len(recall) > 0


def test_recall_ranks_ron_wyden_for_ronald_l_wyden() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Ron Wyden",
            slug="ron-wyden",
        )
        session.add(canon)
        session.commit()
        person = SubstratePerson(
            project_id=pid,
            name="Ronald L. Wyden",
            normalized_name="ronald l wyden",
        )
        recall = retrieve_person_canonical_candidates(
            session, stylebook_id=sb_id, person=person, limit=8
        )
        labels = [label for _cid, label in recall]
        assert "Ron Wyden" in labels


def test_recall_ranks_accent_variant_for_same_affiliation() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="José García",
            slug="jose-garcia",
            affiliation="City Hall",
        )
        session.add(canon)
        session.flush()
        upsert_alias_for_canonical_text(
            session,
            canon_id=str(canon.id),
            alias_text="José García",
            normalized_alias="josé garcía",
            provenance="seed",
        )
        session.commit()
        person = SubstratePerson(
            project_id=pid,
            name="Jose Garcia",
            normalized_name="jose garcia",
            affiliation="City Hall",
        )
        recall = retrieve_person_canonical_candidates(
            session, stylebook_id=sb_id, person=person, limit=8
        )
        assert recall
        assert recall[0][0] == str(canon.id)


def test_alias_hit_with_affiliation_mismatch_defers_not_links() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="John Smith",
            slug="john-smith",
            affiliation="Chicago",
        )
        session.add(canon)
        session.flush()
        upsert_alias_for_canonical_text(
            session,
            canon_id=str(canon.id),
            alias_text="John Smith",
            normalized_alias="john smith",
            provenance="seed",
        )
        person = SubstratePerson(
            project_id=pid,
            name="John Smith",
            normalized_name="john smith",
            affiliation="Evanston",
        )
        session.add(person)
        session.commit()
        session.refresh(person)
        plan = decide_person_canonical_persist_plan(session, stylebook_id=sb_id, person=person)
        assert plan.decision == CanonicalPersistDecision.DEFER


def test_same_affiliation_different_name_does_not_tier1_link() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Faith Hernandez",
            slug="faith-hernandez",
            affiliation="Chicago Housing Authority",
        )
        session.add(canon)
        session.commit()
        person = SubstratePerson(
            project_id=pid,
            name="Keith Pettigrew",
            normalized_name="keith pettigrew",
            title="CEO",
            affiliation="Chicago Housing Authority",
        )
        session.add(person)
        session.commit()
        session.refresh(person)
        plan = decide_person_canonical_persist_plan(session, stylebook_id=sb_id, person=person)
        assert plan.decision != CanonicalPersistDecision.LINK_EXISTING
