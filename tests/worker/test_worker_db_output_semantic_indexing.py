"""Worker Backfield Output semantic indexing integration tests."""

from __future__ import annotations

import os
from unittest.mock import patch

from backfield_db import (
    AgateRun,
    SubstratePersonSemanticDocument,
)
from sqlmodel import Session, SQLModel, create_engine, select
from worker.nodes.db_output import run_db_output
from worker.substrate import persist_from_consolidated

from tests.worker.test_person_substrate_persistence import _sample_person_entry
from tests.worker.test_substrate_persistence import _bootstrap_project, _empty_places


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def test_json_output_runner_does_not_semantically_index() -> None:
    from agate_runtime.nodes.output import run_output

    out = run_output(
        {},
        {
            "consolidated": {
                "text": "Mayor Jane Smith spoke today.",
                "people": [_sample_person_entry()],
            }
        },
    )
    assert "semantic_indexing" not in out


def test_node_runners_use_separate_output_and_db_output() -> None:
    from agate_runtime.nodes import NODE_RUNNERS

    assert NODE_RUNNERS["Output"] is not NODE_RUNNERS["DBOutput"]


def test_persist_without_semantic_setting_does_not_create_semantic_docs() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id = _bootstrap_project(
            session, org_slug="org-sem-off", project_slug="proj-sem-off"
        )
        session.add(AgateRun(id="run-sem-off", graph_id="graph-sem-off", status="pending"))
        session.commit()

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-sem-off",
            run_id="run-sem-off",
            consolidated={
                "text": "Mayor Jane Smith announced a new policy today.",
                "url": "https://example.com/sem-off",
                "places": _empty_places(),
                "people": [_sample_person_entry()],
            },
            db_output_params={"semantic_indexing_enabled": False},
        )
        session.commit()

        docs = session.exec(select(SubstratePersonSemanticDocument)).all()
        assert docs == []


def test_run_db_output_with_semantic_indexing_enabled_creates_semantic_docs() -> None:
    engine = _engine()
    env = {
        "BACKFIELD_PROJECT_ID": "1",
        "BACKFIELD_GRAPH_ID": "graph-sem-on",
        "BACKFIELD_RUN_ID": "run-sem-on",
    }
    consolidated = {
        "text": "Mayor Jane Smith announced a new policy today.",
        "url": "https://example.com/sem-on",
        "people": [_sample_person_entry()],
    }

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-sem-on", project_slug="proj-sem-on")
        session.add(AgateRun(id="run-sem-on", graph_id="graph-sem-on", status="pending"))
        session.commit()
        env["BACKFIELD_PROJECT_ID"] = str(project_id)

    with patch.dict(os.environ, env, clear=False):
        with patch("backfield_db.session.get_engine", return_value=engine):
            out = run_db_output(
                {"semantic_indexing_enabled": True, "stylebook_matching_enabled": False},
                {"data": consolidated},
            )

    assert out["success"] is True
    assert out["semantic_indexing"]["enabled"] is True
    assert out["semantic_indexing"]["status"] == "succeeded"
    assert out["semantic_indexing"]["domains"]
    assert out["semantic_indexing"]["domains"][0]["entity_type"] == "person"
    assert out["semantic_indexing"]["domains"][0]["created"] >= 1

    with Session(engine) as session:
        docs = session.exec(select(SubstratePersonSemanticDocument)).all()
        assert len(docs) >= 1
        assert all(doc.embedding_status == "pending" for doc in docs)


def test_run_db_output_default_semantic_indexing_disabled() -> None:
    engine = _engine()
    env = {
        "BACKFIELD_PROJECT_ID": "1",
        "BACKFIELD_GRAPH_ID": "graph-sem-default",
        "BACKFIELD_RUN_ID": "run-sem-default",
    }
    consolidated = {
        "text": "Mayor Jane Smith announced a new policy today.",
        "url": "https://example.com/sem-default",
        "places": _empty_places(),
        "people": [_sample_person_entry()],
    }

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session, org_slug="org-sem-default", project_slug="proj-sem-default"
        )
        session.add(AgateRun(id="run-sem-default", graph_id="graph-sem-default", status="pending"))
        session.commit()
        env["BACKFIELD_PROJECT_ID"] = str(project_id)

    with patch.dict(os.environ, env, clear=False):
        with patch("backfield_db.session.get_engine", return_value=engine):
            out = run_db_output({}, {"data": consolidated})

    assert out["semantic_indexing"] == {
        "enabled": False,
        "status": "not_enabled",
        "domains": [],
    }

    with Session(engine) as session:
        docs = session.exec(select(SubstratePersonSemanticDocument)).all()
        assert docs == []
