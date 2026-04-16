from __future__ import annotations

from backfield_db import AgateRun, BackfieldOrganization, BackfieldProject
from sqlmodel import Session, SQLModel, col, create_engine, select
from worker.substrate_persistence import persist_from_consolidated

CHICAGO_POINT = {"type": "Point", "coordinates": [-87.6298, 41.8781]}


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
                            "nature": "setting",
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
            BackfieldArticle,
            BackfieldLocation,
            BackfieldLocationMention,
            BackfieldLocationMentionOccurrence,
        )

        articles = session.exec(select(BackfieldArticle)).all()
        assert len(articles) == 1
        assert articles[0].text == "Hello Chicago."
        assert articles[0].source_run_id == "run-1"

        locations = session.exec(select(BackfieldLocation)).all()
        assert len(locations) == 1
        assert locations[0].external_source == "pelias"

        mentions = session.exec(select(BackfieldLocationMention)).all()
        assert len(mentions) == 1
        assert mentions[0].role_in_story == "Setting"
        assert mentions[0].nature == "setting"

        occ = session.exec(select(BackfieldLocationMentionOccurrence)).all()
        assert len(occ) == 1
        assert occ[0].mention_text == "Chicago"
        assert occ[0].suppressed is False
        assert occ[0].context_text == "Mentioned as the setting for the story."
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
        from backfield_db import BackfieldLocationMentionOccurrence

        occ = session.exec(
            select(BackfieldLocationMentionOccurrence).order_by(col(BackfieldLocationMentionOccurrence.id))
        ).all()
        assert len(occ) == 2
        assert sum(1 for row in occ if row.suppressed) == 1
        assert sum(1 for row in occ if not row.suppressed) == 1
