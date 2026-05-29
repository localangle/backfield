"""Worker substrate persistence tests for consolidated ``people`` payloads."""

from __future__ import annotations

from backfield_db import (
    AgateRun,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
)
from backfield_stylebook.canonical_link import CANONICAL_LINK_PENDING
from sqlmodel import Session, SQLModel, col, create_engine, select
from worker.substrate import persist_from_consolidated
from worker.substrate.entities.registry import get_persist_handler, registered_consolidated_keys

from tests.worker.test_substrate_persistence import _bootstrap_project, _empty_places


def _sample_person_entry(*, name: str = "Jane Smith") -> dict:
    return {
        "name": name,
        "title": "Mayor",
        "affiliation": "City of Chicago",
        "public_figure": True,
        "type": "politician",
        "role_in_story": "Announced a new policy",
        "nature": "official",
        "nature_secondary_tags": ["source"],
        "mentions": [
            {"text": "Mayor Jane Smith announced a new policy today.", "quote": False},
            {
                "text": '"This will benefit all residents," Smith said.',
                "quote": True,
            },
        ],
    }


def test_registered_people_handler() -> None:
    assert "people" in registered_consolidated_keys()
    handler = get_persist_handler("people")
    assert handler is not None
    assert handler.consolidated_key == "people"


def test_persist_people_writes_substrate_mention_occurrence() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    body = (
        "Mayor Jane Smith announced a new policy today. "
        '"This will benefit all residents," Smith said.'
    )

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-people", project_slug="proj-people")
        session.add(AgateRun(id="run-p1", graph_id="graph-p1", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-p1",
            run_id="run-p1",
            consolidated={
                "text": body,
                "url": "https://example.com/people-1",
                "places": _empty_places(),
                "people": [_sample_person_entry()],
            },
            db_output_params={"auto_apply_canonicalization": False},
        )
        session.commit()

    with Session(engine) as session:
        people = session.exec(select(SubstratePerson)).all()
        assert len(people) == 1
        person = people[0]
        assert person.name == "Jane Smith"
        assert person.title == "Mayor"
        assert person.affiliation == "City of Chicago"
        assert person.public_figure is True
        assert person.person_type == "politician"
        assert person.identity_fingerprint
        assert person.canonical_link_status == CANONICAL_LINK_PENDING

        mentions = session.exec(select(SubstratePersonMention)).all()
        assert len(mentions) == 1
        assert mentions[0].nature == "official"
        assert mentions[0].nature_secondary_tags_json == ["source"]
        assert mentions[0].role_in_story == "Announced a new policy"

        occ = session.exec(
            select(SubstratePersonMentionOccurrence).order_by(
                col(SubstratePersonMentionOccurrence.occurrence_order)
            )
        ).all()
        assert len(occ) == 2
        assert occ[0].mention_text.startswith("Mayor Jane Smith")
        assert occ[0].quote_text is None
        assert occ[1].quote_text == occ[1].mention_text
        assert "quote" in occ[1].labels_json


def test_persist_empty_people_array_is_noop() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-pe", project_slug="proj-pe")
        session.add(AgateRun(id="run-pe", graph_id="graph-pe", status="pending"))
        session.commit()

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-pe",
            run_id="run-pe",
            consolidated={
                "text": "No people here.",
                "url": "https://example.com/no-people",
                "places": _empty_places(),
                "people": [],
            },
        )
        session.commit()

        assert result.reconciliation_summary.domain == "places"
        people_summaries = [s for s in result.domain_summaries if s.domain == "people"]
        assert len(people_summaries) == 1
        assert people_summaries[0].added == 0

    with Session(engine) as session:
        assert session.exec(select(SubstratePerson)).all() == []


def test_persist_people_only_without_places() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-po", project_slug="proj-po")
        session.add(AgateRun(id="run-po", graph_id="graph-po", status="pending"))
        session.commit()

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-po",
            run_id="run-po",
            consolidated={
                "text": "Jane Smith spoke at the rally.",
                "url": "https://example.com/people-only",
                "people": [_sample_person_entry(name="Jane Smith")],
            },
        )
        session.commit()

        assert result.reconciliation_summary.domain == "people"
        assert result.reconciliation_summary.added == 1

    with Session(engine) as session:
        assert len(session.exec(select(SubstratePerson)).all()) == 1


def test_people_reingest_retires_stale_system_mentions() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    url = "https://example.com/people-rerun"

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-pr", project_slug="proj-pr")
        session.add(AgateRun(id="run-pr1", graph_id="graph-pr", status="pending"))
        session.add(AgateRun(id="run-pr2", graph_id="graph-pr", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-pr",
            run_id="run-pr1",
            consolidated={
                "text": "Jane Smith and John Doe attended.",
                "url": url,
                "people": [
                    _sample_person_entry(name="Jane Smith"),
                    _sample_person_entry(name="John Doe"),
                ],
            },
            db_output_params={"reconciliation_policy": "smart_merge"},
        )
        session.commit()

        old_john = session.exec(
            select(SubstratePerson).where(SubstratePerson.normalized_name == "john doe")
        ).one()
        old_john_id = int(old_john.id)  # type: ignore[arg-type]

        _, retired, disposed, _ = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-pr",
            run_id="run-pr2",
            consolidated={
                "text": "Jane Smith attended alone.",
                "url": url,
                "people": [_sample_person_entry(name="Jane Smith")],
            },
            db_output_params={"reconciliation_policy": "smart_merge"},
        )
        session.commit()

    assert retired == 1
    assert disposed == 1

    with Session(engine) as session:
        assert session.get(SubstratePerson, old_john_id) is None
        active_mentions = session.exec(
            select(SubstratePersonMention).where(
                col(SubstratePersonMention.deleted).is_(False),
            )
        ).all()
        assert len(active_mentions) == 1
