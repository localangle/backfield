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
from backfield_entities.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
)
from backfield_entities.canonical.plan_types import CanonicalPersistDecision
from backfield_entities.entities.person import (
    allocate_unique_person_canonical_slug,
    create_standalone_canonical,
    decide_person_canonical_persist_plan,
    derive_person_sort_key,
    link_substrate_to_canonical_atomic,
    link_to_existing_canonical,
    materialize_new_canonical_and_link,
    maybe_prune_ingest_orphan_person_canonical,
    person_identity_fingerprint,
    rank_canonical_suggestions_for_substrate,
    unlink_substrate_from_canonical,
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
            sort_key="smith",
            title="Mayor",
            affiliation="City of Chicago",
            public_figure=True,
            person_type="politician",
            identity_fingerprint=person_identity_fingerprint(
                normalized_name="john smith",
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
        assert canon.sort_key == "smith"
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


def test_person_identity_fingerprint_uses_accent_folded_name_and_affiliation() -> None:
    fp_accent = person_identity_fingerprint(
        normalized_name="josé garcía",
        affiliation="Mets",
    )
    fp_plain = person_identity_fingerprint(
        normalized_name="jose garcia",
        affiliation="Mets",
    )
    assert fp_accent == fp_plain

    fp_mets = person_identity_fingerprint(
        normalized_name="joe smith",
        affiliation="Mets",
    )
    fp_yanks = person_identity_fingerprint(
        normalized_name="joe smith",
        affiliation="Yankees",
    )
    assert fp_mets != fp_yanks

    fp_mayor = person_identity_fingerprint(
        normalized_name="john smith",
        affiliation="Chicago",
    )
    fp_resident = person_identity_fingerprint(
        normalized_name="john smith",
        affiliation="Chicago",
    )
    assert fp_mayor == fp_resident


def test_person_identity_fingerprint_splits_generational_suffixes() -> None:
    fp_jr = person_identity_fingerprint(normalized_name="emil jones jr")
    fp_iii = person_identity_fingerprint(normalized_name="emil jones iii")
    assert fp_jr != fp_iii


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


def test_decide_person_links_accent_variant_with_same_affiliation() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="José García",
            slug="jose-garcia",
            title="Director",
            affiliation="Natural Resources Defense Council",
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
        person = SubstratePerson(
            project_id=pid,
            name="Jose Garcia",
            normalized_name="jose garcia",
            title="Director",
            affiliation="Natural Resources Defense Council",
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        plan = decide_person_canonical_persist_plan(session, stylebook_id=sb_id, person=person)
        assert plan.decision == CanonicalPersistDecision.LINK_EXISTING
        assert plan.existing_canonical_id == str(canon.id)


def test_decide_person_defers_when_accent_variant_but_affiliation_differs() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        canon = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Gina Ramirez",
            slug="gina-ramirez",
            affiliation="Midwest Environmental Health, Natural Resources Defense Council",
        )
        session.add(canon)
        session.flush()
        upsert_alias_for_canonical_text(
            session,
            canon_id=str(canon.id),
            alias_text="Gina Ramirez",
            normalized_alias="gina ramirez",
            provenance="seed",
        )
        person = SubstratePerson(
            project_id=pid,
            name="Gina Ramírez",
            normalized_name="gina ramírez",
            affiliation="Natural Resources Defense Council",
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        plan = decide_person_canonical_persist_plan(session, stylebook_id=sb_id, person=person)
        assert plan.decision == CanonicalPersistDecision.DEFER


def test_decide_person_defers_when_alias_matches_but_affiliation_differs() -> None:
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
        codes = [
            str(r.get("code"))
            for r in plan.resolution_reasons
            if isinstance(r, dict)
        ]
        assert "ambiguous_person_canonical_match" in codes
        recall = next(
            r.get("recall_canonical_ids")
            for r in plan.resolution_reasons
            if isinstance(r, dict) and r.get("code") == "ambiguous_person_canonical_match"
        )
        assert isinstance(recall, list)
        assert str(canon.id) in [str(x) for x in recall]


def test_decide_person_materializes_when_no_canonical_match() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        person = SubstratePerson(
            project_id=pid,
            name="New Person",
            normalized_name="new person",
            title="Mayor",
            affiliation="Springfield",
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
        assert plan.decision == CanonicalPersistDecision.MATERIALIZE_NEW


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


def test_unlink_prunes_ingest_orphan_canonical_when_last_substrate_removed() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        person = SubstratePerson(
            project_id=pid,
            name="Alex Bregman",
            normalized_name="alex bregman",
            title="Player",
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        materialize_new_canonical_and_link(session, stylebook_id=sb_id, person=person)
        session.commit()
        session.refresh(person)
        ghost_id = str(person.stylebook_person_canonical_id)
        assert ghost_id

        unlink_substrate_from_canonical(
            session,
            stylebook_id=sb_id,
            person=person,
            provenance="agate_superseded_ingest",
            requeue_after_unlink=False,
        )
        session.commit()

        assert session.get(StylebookPersonCanonical, ghost_id) is None
        assert (
            session.exec(
                select(StylebookPersonAlias).where(
                    StylebookPersonAlias.person_canonical_id == ghost_id
                )
            ).first()
            is None
        )


def test_unlink_keeps_manual_canonical_with_zero_substrates() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, pid = _seed_stylebook(session)
        canon = create_standalone_canonical(
            session,
            stylebook_id=sb_id,
            label="Catalog Only",
            provenance="stylebook_ui_manual",
        )
        session.commit()
        canon_id = str(canon.id)
        person = SubstratePerson(
            project_id=pid,
            name="Catalog Only",
            normalized_name="catalog only",
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        session.add(person)
        session.commit()
        session.refresh(person)

        link_substrate_to_canonical_atomic(
            session,
            stylebook_id=sb_id,
            person=person,
            target_canonical_id=canon_id,
            provenance="stylebook_ui_link",
        )
        session.commit()
        session.refresh(person)

        unlink_substrate_from_canonical(
            session,
            stylebook_id=sb_id,
            person=person,
            provenance="stylebook_ui_unlink",
            requeue_after_unlink=True,
        )
        session.commit()

        assert session.get(StylebookPersonCanonical, canon_id) is not None


def test_maybe_prune_skips_aliasless_legacy_canonical_without_ingest_signal() -> None:
    engine = _engine()
    with Session(engine) as session:
        sb_id, _pid = _seed_stylebook(session)
        legacy = StylebookPersonCanonical(
            stylebook_id=sb_id,
            label="Legacy Import",
            slug="legacy-import",
        )
        session.add(legacy)
        session.commit()
        session.refresh(legacy)
        legacy_id = str(legacy.id)

        pruned = maybe_prune_ingest_orphan_person_canonical(
            session,
            stylebook_id=sb_id,
            canonical_id=legacy_id,
            removed_substrate_ingest_alias=False,
        )
        session.commit()

        assert pruned is False
        assert session.get(StylebookPersonCanonical, legacy_id) is not None


def test_derive_person_sort_key_uses_last_name() -> None:
    assert derive_person_sort_key("Jane Doe") == "doe"
    assert derive_person_sort_key("Madonna") == "madonna"
    assert derive_person_sort_key("Jane Doe", explicit="Custom") == "custom"
    assert derive_person_sort_key("Jane Doe", name_last="Doe") == "doe"
