from __future__ import annotations

from backfield_db import AgateRun, BackfieldOrganization, BackfieldProject
from sqlmodel import Session, SQLModel, col, create_engine, select
from worker.substrate_persistence import _find_mention_span, persist_from_consolidated

CHICAGO_POINT = {"type": "Point", "coordinates": [-87.6298, 41.8781]}


def test_find_mention_span_strips_trailing_punctuation_not_in_article() -> None:
    haystack = (
        "Violet Harris, a 15-year-old student, was killed after a vehicle crashed into "
        "the electric scooter she was riding last month in South Shore"
    )
    needle = haystack + "."
    assert haystack.find(needle) < 0
    span = _find_mention_span(haystack=haystack, needle=needle)
    assert span is not None
    start, end = span
    assert haystack[start:end] == haystack
    assert end == len(haystack)


def test_find_mention_span_exact_match_still_preferred() -> None:
    haystack = "We met in South Shore."
    assert _find_mention_span(haystack=haystack, needle="South Shore.") == (10, 22)


def test_find_mention_span_unifies_curly_and_straight_quotes() -> None:
    haystack = 'He was "still processing" the news.'
    needle = "He was 'still processing' the news."
    span = _find_mention_span(haystack=haystack, needle=needle)
    assert span == (0, len(haystack))


def test_find_mention_span_falls_back_when_paraphrase_differs() -> None:
    haystack = (
        'Ald. Desmon Yancy (5th) said Thursday morning he was "still processing" '
        "the shooting in his ward."
    )
    needle = (
        "Fifth Ward Ald. Desmon Yancy said Thursday morning he was 'still processing' "
        "the shooting in his ward."
    )
    span = _find_mention_span(haystack=haystack, needle=needle)
    assert span is not None
    start, end = span
    excerpt = haystack[start:end]
    assert len(excerpt) >= 12
    assert excerpt in haystack
    assert "still processing" in excerpt or "Desmon Yancy" in excerpt


def _bootstrap_project(session: Session, *, org_slug: str, project_slug: str) -> int:
    org = BackfieldOrganization(name="Org", slug=org_slug)
    session.add(org)
    session.commit()
    session.refresh(org)

    proj = BackfieldProject(organization_id=int(org.id), name="Proj", slug=project_slug)  # type: ignore[arg-type]
    session.add(proj)
    session.commit()
    session.refresh(proj)

    return int(proj.id)  # type: ignore[arg-type]


def test_persist_graph_outputs_writes_article_location_mention_occurrence() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org", project_slug="proj")
        session.add(AgateRun(id="run-1", graph_id="graph-1", status="pending"))
        session.commit()

        consolidated = {
            "text": "Hello Chicago.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:1",
                            "original_text": "Chicago",
                            "description": "Mentioned as the setting for the story.",
                            "role_in_story": "Setting",
                            "nature": "primary",
                            "nature_secondary_tags": ["context"],
                            "location": "Chicago, IL",
                            "type": "city",
                            "geocode": {
                                "geocode_type": "pelias",
                                "result": {
                                    "id": "pelias:abc",
                                    "formatted_address": "Chicago, IL, USA",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-1",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import (
            SubstrateArticle,
            SubstrateLocation,
            SubstrateLocationMention,
            SubstrateLocationMentionOccurrence,
        )

        articles = session.exec(select(SubstrateArticle)).all()
        assert len(articles) == 1
        assert articles[0].text == "Hello Chicago."
        assert articles[0].source_run_id == "run-1"

        locations = session.exec(select(SubstrateLocation)).all()
        assert len(locations) == 1
        assert locations[0].external_source == "pelias"

        mentions = session.exec(select(SubstrateLocationMention)).all()
        assert len(mentions) == 1
        assert mentions[0].role_in_story == "Setting"
        assert mentions[0].nature == "primary"
        assert mentions[0].nature_secondary_tags_json == ["context"]

        occ = session.exec(select(SubstrateLocationMentionOccurrence)).all()
        assert len(occ) == 1
        assert occ[0].mention_text == "Chicago"
        assert occ[0].suppressed is False
        assert occ[0].start_char == 6
        assert occ[0].end_char == 13
        assert occ[0].occurrence_order == 0


def test_persist_graph_outputs_suppresses_prior_occurrences_on_repeat() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org2", project_slug="proj2")
        session.add(AgateRun(id="run-1", graph_id="graph-1", status="pending"))
        session.add(AgateRun(id="run-2", graph_id="graph-1", status="pending"))
        session.commit()

        consolidated = {
            "text": "Hello Chicago.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [
                        {
                            "id": "city:1",
                            "original_text": "Chicago",
                            "location": "Chicago, IL",
                            "type": "city",
                            "geocode": {
                                "geocode_type": "pelias",
                                "result": {
                                    "id": "pelias:abc",
                                    "formatted_address": "Chicago, IL, USA",
                                    "geometry": CHICAGO_POINT,
                                },
                            },
                        }
                    ],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [],
                "needs_review": [],
            },
        }
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-1",
            consolidated=consolidated,
        )
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-2",
            consolidated=consolidated,
        )
        session.commit()

    with Session(engine) as session:
        from backfield_db import SubstrateLocationMentionOccurrence

        occ = session.exec(
            select(SubstrateLocationMentionOccurrence).order_by(
                col(SubstrateLocationMentionOccurrence.id)
            )
        ).all()
        assert len(occ) == 2
        assert sum(1 for row in occ if row.suppressed) == 1
        assert sum(1 for row in occ if not row.suppressed) == 1
