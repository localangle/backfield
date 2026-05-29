"""Tests for Stylebook person canonical persist and link helpers."""

from __future__ import annotations

from uuid import UUID

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookPersonAlias,
    StylebookPersonCanonical,
    SubstratePerson,
)
from backfield_stylebook.canonical.link import CANONICAL_LINK_LINKED, CANONICAL_LINK_PENDING
from backfield_stylebook.canonical.policy import CanonicalPersistDecision
from backfield_stylebook.entities.person import (
    allocate_unique_person_canonical_slug,
    decide_person_canonical_persist_plan,
    link_substrate_to_canonical_atomic,
    link_to_existing_canonical,
    materialize_new_canonical_and_link,
    person_identity_fingerprint,
    rank_canonical_suggestions_for_substrate,
    upsert_alias_for_canonical_text,
)
from sqlmodel import Session, SQLModel, create_engine, select


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_stylebook(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-person-persist")
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = Stylebook(organization_id=oid, slug="default", name="Default", is_default=True)
    session.add(sb)
    session.commit()
    session.refresh(sb)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    proj = BackfieldProject(name="Demo", slug="demo-person", organization_id=oid)
    session.add(proj)
    session.commit()
    session.refresh(proj)
    return sb_id, int(proj.id)  # type: ignore[arg-type]


def test_allocate_unique_person_canonical_slug_suffixes_on_collision() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, _pid = _seed_stylebook(session)
        slug = allocate_unique_person_canonical_slug(
            session, stylebook_id=sb_id, label="Jane Doe"
        )
        assert slug == "jane-doe"
        session.add(
            StylebookPersonCanonical(
                stylebook_id=sb_id,
                label="Jane Doe",
                slug="jane-doe",
            )
        )
        session.commit()
        assert (
            allocate_unique_person_canonical_slug(session, stylebook_id=sb_id, label="Jane Doe")
            == "jane-doe-2"
        )


def test_materialize_new_canonical_and_link_mirrors_fields() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        person = SubstratePerson(
            project_id=pid,
            name="John Smith",
            normalized_name="john smith",
            title="Mayor",
            affiliation="City of Chicago",
            public_figure=True,
            person_type="politician",
            identity_fingerprint=person_identity_fingerprint(
                normalized_name="john smith",
                title="Mayor",
                affiliation="City of Chicago",
            ),
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        materialize_new_canonical_and_link(session, stylebook_id=sb_id, person=person)
        session.commit()
        session.refresh(person)

        assert person.stylebook_person_canonical_id is not None
        assert person.canonical_link_status == CANONICAL_LINK_LINKED
        canon = session.get(StylebookPersonCanonical, str(person.stylebook_person_canonical_id))
        assert canon is not None
        UUID(canon.id)
        assert canon.label == "John Smith"
        assert canon.title == "Mayor"
        assert canon.affiliation == "City of Chicago"
        assert canon.public_figure is True
        assert canon.person_type == "politician"
        aliases = session.exec(
            select(StylebookPersonAlias).where(
                StylebookPersonAlias.person_canonical_id == str(canon.id)
            )
        ).all()
        assert len(aliases) == 1
        assert aliases[0].normalized_alias == "john smith"


def test_link_to_existing_canonical_records_alias_when_name_differs() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Jane Doe",
            slug="jane-doe",
            title="Resident",
            affiliation="Chicago",
        )
        session.add(canon)
        session.flush()
        upsert_alias_for_canonical_text(
            session,
            canon_id=str(canon.id),
            alias_text="Jane Doe",
            normalized_alias="jane doe",
            provenance="seed",
        )
        person = SubstratePerson(
            project_id=pid,
            name="J. Doe",
            normalized_name="j. doe",
            title="Resident",
            affiliation="Chicago",
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        link_to_existing_canonical(
            session,
            stylebook_id=sb_id,
            person=person,
            canonical_id=str(canon.id),
        )
        session.commit()
        session.refresh(person)

        assert person.stylebook_person_canonical_id == str(canon.id)
        aliases = session.exec(
            select(StylebookPersonAlias).where(
                StylebookPersonAlias.person_canonical_id == str(canon.id)
            )
        ).all()
        norms = {a.normalized_alias for a in aliases}
        assert "j. doe" in norms


def test_person_identity_fingerprint_distinguishes_title_and_affiliation() -> None:
    fp1 = person_identity_fingerprint(
        normalized_name="john smith",
        title="Mayor",
        affiliation="Chicago",
    )
    fp2 = person_identity_fingerprint(
        normalized_name="john smith",
        title="Resident",
        affiliation="Chicago",
    )
    fp3 = person_identity_fingerprint(
        normalized_name="john smith",
        title="Mayor",
        affiliation="Chicago",
    )
    assert fp1 != fp2
    assert fp1 == fp3


def test_decide_person_canonical_persist_plan_links_exact_identity() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Sam Rivera",
            slug="sam-rivera",
            title="Shortstop",
            affiliation="Chicago Cubs",
        )
        session.add(canon)
        session.commit()
        person = SubstratePerson(
            project_id=pid,
            name="Sam Rivera",
            normalized_name="sam rivera",
            title="Shortstop",
            affiliation="Chicago Cubs",
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        plan = decide_person_canonical_persist_plan(
            session,
            stylebook_id=sb_id,
            person=person,
            auto_apply_canonicalization=False,
        )
        assert plan.decision == CanonicalPersistDecision.LINK_EXISTING
        assert plan.existing_canonical_id == str(canon.id)


def test_decide_person_defer_when_alias_matches_but_identity_differs() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="John Smith",
            slug="john-smith",
            title="Mayor",
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
            title="Resident",
            affiliation="Evanston",
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        plan = decide_person_canonical_persist_plan(session, stylebook_id=sb_id, person=person)
        assert plan.decision == CanonicalPersistDecision.DEFER


def test_link_substrate_to_canonical_atomic_is_idempotent() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Maria Garcia",
            slug="maria-garcia",
        )
        session.add(canon)
        session.commit()
        person = SubstratePerson(
            project_id=pid,
            name="Maria Garcia",
            normalized_name="maria garcia",
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        changed = link_substrate_to_canonical_atomic(
            session,
            stylebook_id=sb_id,
            person=person,
            target_canonical_id=str(canon.id),
        )
        assert changed is True
        session.commit()
        session.refresh(person)
        again = link_substrate_to_canonical_atomic(
            session,
            stylebook_id=sb_id,
            person=person,
            target_canonical_id=str(canon.id),
        )
        assert again is False


def test_rank_canonical_suggestions_prefers_exact_alias() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        exact = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Jane Doe",
            slug="jane-doe",
        )
        other = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Jane D.",
            slug="jane-d",
        )
        session.add(exact)
        session.add(other)
        session.flush()
        upsert_alias_for_canonical_text(
            session,
            canon_id=str(exact.id),
            alias_text="Jane Doe",
            normalized_alias="jane doe",
            provenance="seed",
        )
        person = SubstratePerson(
            project_id=pid,
            name="Jane Doe",
            normalized_name="jane doe",
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        ranked = rank_canonical_suggestions_for_substrate(
            session,
            stylebook_id=sb_id,
            person=person,
            limit=5,
        )
        assert ranked
        assert ranked[0][0] == str(exact.id)
