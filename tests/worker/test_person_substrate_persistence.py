"""Worker substrate persistence tests for consolidated ``people`` payloads."""

from __future__ import annotations

import json
from unittest.mock import patch

from agate_runtime import execute_graph
from agate_runtime.starter_flow import starter_people_flow_graph_spec
from backfield_db import (
    AgateRun,
    BackfieldProject,
    Stylebook,
    StylebookPersonAlias,
    StylebookPersonCanonical,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
    SubstratePersonSemanticDocument,
)
from backfield_db.semantic_indexing import SEMANTIC_EMBEDDING_STATUS_PENDING
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING
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
        "type": "elected_official",
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
        assert person.person_type == "elected_official"
        assert person.sort_key == "smith"
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


def test_people_rerun_revalidates_existing_link_before_alias_refresh() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    url = "https://example.com/people-revalidate"
    body = "Mayor Jane Smith announced a new policy today."

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-people-revalidate",
            project_slug="proj-people-revalidate",
        )
        project = session.get(BackfieldProject, project_id)
        assert project is not None
        stylebook = session.exec(
            select(Stylebook).where(Stylebook.organization_id == project.organization_id)
        ).one()
        wrong_canonical = StylebookPersonCanonical(
            stylebook_id=int(stylebook.id),
            label="Tre Jones",
            slug="tre-jones-rerun-gate",
            status="active",
        )
        session.add(wrong_canonical)
        session.add_all(
            (
                AgateRun(id="run-person-link-a", graph_id="graph-person-link", status="pending"),
                AgateRun(id="run-person-link-b", graph_id="graph-person-link", status="pending"),
            )
        )
        session.commit()

        payload = {
            "text": body,
            "url": url,
            "people": [_sample_person_entry(name="Jane Smith")],
        }
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-person-link",
            run_id="run-person-link-a",
            consolidated=payload,
            db_output_params={
                "auto_apply_canonicalization": False,
                "stylebook_id": int(stylebook.id),
            },
        )
        person = session.exec(select(SubstratePerson)).one()
        person.stylebook_person_canonical_id = str(wrong_canonical.id)
        person.canonical_link_status = "linked"
        session.add(person)
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-person-link",
            run_id="run-person-link-b",
            consolidated=payload,
            db_output_params={
                "auto_apply_canonicalization": True,
                "stylebook_id": int(stylebook.id),
            },
        )
        session.commit()

        session.refresh(person)
        assert person.stylebook_person_canonical_id != str(wrong_canonical.id)
        poisoned_aliases = session.exec(
            select(StylebookPersonAlias).where(
                StylebookPersonAlias.person_canonical_id == str(wrong_canonical.id),
                StylebookPersonAlias.normalized_alias == "jane smith",
            )
        ).all()
        assert poisoned_aliases == []


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
        john_mention = session.exec(
            select(SubstratePersonMention).where(
                SubstratePersonMention.person_id == old_john_id,
                SubstratePersonMention.deleted == False,  # noqa: E712
            )
        ).one()
        john_occ = session.exec(
            select(SubstratePersonMentionOccurrence).where(
                SubstratePersonMentionOccurrence.person_mention_id == int(john_mention.id)
            )
        ).first()
        assert john_occ is not None
        session.add(
            SubstratePersonSemanticDocument(
                project_id=project_id,
                article_id=int(john_mention.article_id),
                person_id=old_john_id,
                person_mention_id=int(john_mention.id),
                person_mention_occurrence_id=int(john_occ.id),
                search_text="John Doe",
                source_hash="hash-john-sem",
                embedding_status=SEMANTIC_EMBEDDING_STATUS_PENDING,
            )
        )
        session.commit()

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


def test_people_replace_reconciles_omissions_and_preserves_editorial_associations() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    primary_url = "https://example.com/people-replace-primary"
    shared_url = "https://example.com/people-replace-shared"

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-person-replace",
            project_slug="proj-person-replace",
        )
        for run_id in ("run-person-r1", "run-person-r2", "run-person-r3"):
            session.add(AgateRun(id=run_id, graph_id="graph-person-replace", status="pending"))
        session.commit()

        initial_names = [
            "Kept Person",
            "Orphan Person",
            "Shared Person",
            "Edited Person",
            "Added Person",
            "Manual Person",
        ]
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-person-replace",
            run_id="run-person-r1",
            consolidated={
                "text": "Several people appeared in the first story.",
                "url": primary_url,
                "people": [_sample_person_entry(name=name) for name in initial_names],
            },
            db_output_params={"reconciliation_policy": "smart_merge"},
        )
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-person-replace",
            run_id="run-person-r2",
            consolidated={
                "text": "Shared Person appeared in another story.",
                "url": shared_url,
                "people": [_sample_person_entry(name="Shared Person")],
            },
            db_output_params={"reconciliation_policy": "smart_merge"},
        )

        people_by_name = {
            person.normalized_name: person for person in session.exec(select(SubstratePerson)).all()
        }
        mentions_by_name = {}
        for normalized_name in ("edited person", "added person", "manual person"):
            person = people_by_name[normalized_name]
            mentions_by_name[normalized_name] = session.exec(
                select(SubstratePersonMention).where(
                    SubstratePersonMention.person_id == int(person.id),
                )
            ).one()
        mentions_by_name["edited person"].edited = True
        mentions_by_name["added person"].added = True
        mentions_by_name["manual person"].source_kind = "manual"
        for mention in mentions_by_name.values():
            session.add(mention)

        shared_person = people_by_name["shared person"]
        shared_mentions = session.exec(
            select(SubstratePersonMention).where(
                SubstratePersonMention.person_id == int(shared_person.id),
            )
        ).all()
        primary_shared_mention = next(
            mention
            for mention in shared_mentions
            if "run-person-r1" == (mention.source_details_json or {}).get("run_id")
        )
        session.add(
            SubstratePersonMentionOccurrence(
                person_mention_id=int(primary_shared_mention.id),
                source_kind="editorial",
                mention_text="Shared Person editorial evidence",
            )
        )
        session.commit()

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-person-replace",
            run_id="run-person-r3",
            consolidated={
                "text": "Only Kept Person remains.",
                "url": primary_url,
                "people": [_sample_person_entry(name="Kept Person")],
            },
            db_output_params={"reconciliation_policy": "replace"},
        )
        session.commit()

        summary = next(item for item in result.domain_summaries if item.domain == "people")
        assert summary.removed == 2
        assert summary.preserved == 3
        assert summary.disposed == 1
        assert result.retired_mentions == 2
        assert result.disposed_substrates == 1

    with Session(engine) as session:
        remaining_names = {
            person.normalized_name for person in session.exec(select(SubstratePerson)).all()
        }
        assert "orphan person" not in remaining_names
        assert {
            "kept person",
            "shared person",
            "edited person",
            "added person",
            "manual person",
        }.issubset(remaining_names)

        shared_person = session.exec(
            select(SubstratePerson).where(SubstratePerson.normalized_name == "shared person")
        ).one()
        retired_shared_mention = session.exec(
            select(SubstratePersonMention).where(
                SubstratePersonMention.person_id == int(shared_person.id),
                SubstratePersonMention.deleted == True,  # noqa: E712
            )
        ).one()
        occurrences = session.exec(
            select(SubstratePersonMentionOccurrence).where(
                SubstratePersonMentionOccurrence.person_mention_id
                == int(retired_shared_mention.id),
            )
        ).all()
        system_occurrences = [
            occurrence
            for occurrence in occurrences
            if occurrence.source_kind == "system_extraction"
        ]
        editorial_occurrences = [
            occurrence for occurrence in occurrences if occurrence.source_kind == "editorial"
        ]
        assert system_occurrences
        assert all(occurrence.suppressed for occurrence in system_occurrences)
        assert len(editorial_occurrences) == 1
        assert editorial_occurrences[0].suppressed is False


def test_people_replace_empty_array_retires_and_disposes_machine_association() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    url = "https://example.com/people-replace-empty"

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-person-empty",
            project_slug="proj-person-empty",
        )
        session.add(AgateRun(id="run-person-e1", graph_id="graph-person-empty", status="pending"))
        session.add(AgateRun(id="run-person-e2", graph_id="graph-person-empty", status="pending"))
        session.commit()
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-person-empty",
            run_id="run-person-e1",
            consolidated={
                "text": "Temporary Person appeared.",
                "url": url,
                "people": [_sample_person_entry(name="Temporary Person")],
            },
        )
        session.commit()

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-person-empty",
            run_id="run-person-e2",
            consolidated={"text": "Nobody appeared.", "url": url, "people": []},
            db_output_params={"reconciliation_policy": "replace"},
        )
        session.commit()

        summary = next(item for item in result.domain_summaries if item.domain == "people")
        assert summary.removed == 1
        assert summary.disposed == 1
        assert session.exec(select(SubstratePerson)).all() == []


def _mock_people_demo_json() -> str:
    return json.dumps(
        {
            "people": [
                {
                    "name": "John Smith",
                    "title": "Mayor",
                    "affiliation": "Chicago",
                    "public_figure": True,
                    "type": "elected_official",
                    "role_in_story": "Announced park initiative",
                    "nature": "official",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": "Mayor John Smith of Chicago announced a new park initiative.",
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Jane Doe",
                    "title": "",
                    "affiliation": "",
                    "public_figure": False,
                    "type": "community member",
                    "role_in_story": "Resident supporting the plan",
                    "nature": "affected",
                    "nature_secondary_tags": ["source"],
                    "mentions": [
                        {
                            "text": "Jane Doe, a local resident, said she supports the plan.",
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Robert Lee",
                    "title": "",
                    "affiliation": "",
                    "public_figure": False,
                    "type": "other",
                    "role_in_story": "Arrested in vandalism case",
                    "nature": "suspect",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {
                            "text": "Police arrested Robert Lee in connection with vandalism.",
                            "quote": False,
                        }
                    ],
                },
                {
                    "name": "Maria Garcia",
                    "title": "",
                    "affiliation": "",
                    "public_figure": False,
                    "type": "other",
                    "role_in_story": "Witnessed vandalism",
                    "nature": "witness",
                    "nature_secondary_tags": [],
                    "mentions": [
                        {"text": "Maria Garcia witnessed the incident.", "quote": False}
                    ],
                },
            ]
        }
    )


def test_person_extract_pipeline_persist_to_substrate() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-pe2", project_slug="proj-pe2")
        session.add(AgateRun(id="run-pe2", graph_id="graph-pe2", status="pending"))
        session.commit()

        spec = starter_people_flow_graph_spec()
        with patch(
            "agate_nodes.person_extract.node_port.call_llm",
            return_value=_mock_people_demo_json(),
        ):
            out = execute_graph(spec)
        body = out["stylebook_output"]
        assert body["success"] is True
        assert len(body["people"]) >= 4

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-pe2",
            run_id="run-pe2",
            consolidated=body,
            db_output_params={"auto_apply_canonicalization": False},
        )
        session.commit()

    with Session(engine) as session:
        people = session.exec(select(SubstratePerson)).all()
        assert len(people) >= 4
        mentions = session.exec(select(SubstratePersonMention)).all()
        assert len(mentions) >= 4
        natures = {m.nature for m in mentions if m.nature}
        assert "official" in natures
        assert "witness" in natures
        assert "suspect" in natures
