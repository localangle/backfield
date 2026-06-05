"""Worker ingest: person review_handling routes canonical link status."""

from __future__ import annotations

from backfield_db import AgateRun, SubstratePerson, SubstratePersonMention
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED
from backfield_entities.entities.person.review import REASON_ANIMAL, REASON_CHILD
from sqlmodel import Session, SQLModel, create_engine, select
from worker.substrate import persist_from_consolidated

from tests.worker.test_substrate_persistence import _bootstrap_project, _empty_places


def _person_entry(
    *,
    name: str,
    review_handling: str,
    review_reason_code: str,
    review_message: str,
) -> dict:
    return {
        "name": name,
        "title": "",
        "affiliation": "",
        "public_figure": False,
        "type": "",
        "role_in_story": "Mentioned",
        "nature": "other",
        "nature_secondary_tags": [],
        "review_handling": review_handling,
        "review_reason_code": review_reason_code,
        "review_message": review_message,
        "mentions": [{"text": f"{name} was mentioned in the story.", "quote": False}],
    }


def test_persist_child_auto_apply_waived_and_mention_not_flagged() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-pch", project_slug="proj-pch")
        session.add(AgateRun(id="run-pch", graph_id="graph-1", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-pch",
            consolidated={
                "text": "Timmy Larson, 8, was unharmed.",
                "places": _empty_places(),
                "people": [
                    _person_entry(
                        name="Timmy Larson",
                        review_handling="auto_defer",
                        review_reason_code=REASON_CHILD,
                        review_message="Identified as a child",
                    )
                ],
            },
            db_output_params={
                "canonicalization_mode": "rules",
                "auto_apply_canonicalization": True,
            },
        )
        session.commit()

    with Session(engine) as session:
        person = session.exec(select(SubstratePerson)).one()
        assert person.canonical_link_status == CANONICAL_LINK_WAIVED
        mention = session.exec(select(SubstratePersonMention)).one()
        assert mention.needs_review is False


def test_persist_flag_review_open_pending_with_needs_review_mention() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-pfl", project_slug="proj-pfl")
        session.add(AgateRun(id="run-pfl", graph_id="graph-1", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-pfl",
            consolidated={
                "text": "Prince performed last year.",
                "places": _empty_places(),
                "people": [
                    _person_entry(
                        name="Prince",
                        review_handling="flag_review",
                        review_reason_code="stage_name_or_alias",
                        review_message="Stage name or alias",
                    )
                ],
            },
            db_output_params={
                "canonicalization_mode": "rules",
                "auto_apply_canonicalization": True,
            },
        )
        session.commit()

    with Session(engine) as session:
        person = session.exec(select(SubstratePerson)).one()
        assert person.canonical_link_status == CANONICAL_LINK_PENDING
        mention = session.exec(select(SubstratePersonMention)).one()
        assert mention.needs_review is True


def test_persist_alias_affiliation_mismatch_stays_pending() -> None:
    from backfield_db import StylebookPersonCanonical
    from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
    from backfield_entities.entities.person.persist import upsert_alias_for_canonical_text

    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-pam", project_slug="proj-pam")
        from backfield_db import BackfieldOrganization, BackfieldProject

        proj = session.get(BackfieldProject, project_id)
        assert proj is not None
        org = session.get(BackfieldOrganization, proj.organization_id)
        assert org is not None
        sb = ensure_default_stylebook_for_organization(session, int(org.id))  # type: ignore[arg-type]
        canon = StylebookPersonCanonical(
            stylebook_id=int(sb.id),  # type: ignore[arg-type]
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
        session.add(AgateRun(id="run-pam", graph_id="graph-1", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-pam",
            consolidated={
                "text": "John Smith of Evanston spoke.",
                "places": _empty_places(),
                "people": [
                    {
                        "name": "John Smith",
                        "title": "",
                        "affiliation": "Evanston",
                        "public_figure": False,
                        "type": "",
                        "role_in_story": "Quoted",
                        "nature": "source",
                        "nature_secondary_tags": [],
                        "review_handling": "none",
                        "mentions": [
                            {"text": "John Smith of Evanston spoke.", "quote": False}
                        ],
                    }
                ],
            },
            db_output_params={
                "canonicalization_mode": "rules",
                "auto_apply_canonicalization": True,
            },
        )
        session.commit()

    with Session(engine) as session:
        person = session.exec(select(SubstratePerson)).one()
        assert person.canonical_link_status == CANONICAL_LINK_PENDING
        raw = person.canonical_review_reasons_json
        assert isinstance(raw, list)
        assert any(
            isinstance(x, dict) and x.get("code") == "ambiguous_person_canonical_match"
            for x in raw
        )


def test_persist_animal_auto_apply_waived() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-pan", project_slug="proj-pan")
        session.add(AgateRun(id="run-pan", graph_id="graph-1", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-pan",
            consolidated={
                "text": "The dog Buddy was fine.",
                "places": _empty_places(),
                "people": [
                    _person_entry(
                        name="Buddy",
                        review_handling="auto_defer",
                        review_reason_code=REASON_ANIMAL,
                        review_message="Identified as an animal",
                    )
                ],
            },
            db_output_params={"auto_apply_canonicalization": True},
        )
        session.commit()

    with Session(engine) as session:
        person = session.exec(select(SubstratePerson)).one()
        assert person.canonical_link_status == CANONICAL_LINK_WAIVED
