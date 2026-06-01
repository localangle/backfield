"""Person canonical recall (alias-first, capped candidates)."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookPersonCanonical,
    SubstratePerson,
)
from backfield_stylebook.canonical.plan_types import CanonicalPersistDecision
from backfield_stylebook.entities.person.persist import upsert_alias_for_canonical_text
from backfield_stylebook.entities.person.policy import (
    decide_person_canonical_persist_plan,
    person_strong_identity_matches_canonical,
)
from backfield_stylebook.entities.person.recall import (
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
