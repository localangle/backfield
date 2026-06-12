"""DBOutput persistence when only custom_records is present (no entity extract nodes)."""

from __future__ import annotations

import os
from unittest.mock import patch

from backfield_db import (
    AgateRun,
    SubstrateArticle,
    SubstrateCustomRecord,
)
from sqlmodel import Session, SQLModel, create_engine, select
from worker.nodes.db_output import run_db_output
from worker.substrate import persist_from_consolidated

from tests.worker.test_substrate_persistence import _bootstrap_project


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _sample_custom_records() -> dict:
    return {
        "ingredients": {
            "label": "Ingredients",
            "schema": [
                {"name": "item", "label": "Item", "type": "string", "description": ""},
                {"name": "quantity", "label": "Quantity", "type": "string", "description": ""},
            ],
            "records": [
                {
                    "key": "key-flour",
                    "fields": {"item": "flour", "quantity": "2 cups"},
                    "mentions": [{"text": "2 cups of flour, sifted", "quote": False}],
                    "confidence": 0.95,
                }
            ],
            "dropped_ungrounded": 0,
        }
    }


def test_persist_from_consolidated_accepts_custom_records_only() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-custom-only",
            project_slug="proj-custom-only",
        )
        session.add(AgateRun(id="run-custom-only", graph_id="graph-custom-only", status="pending"))
        session.commit()

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-custom-only",
            run_id="run-custom-only",
            consolidated={
                "text": "Story body text.",
                "headline": "Headline",
                "url": "https://example.com/custom-only",
                "custom_records": _sample_custom_records(),
            },
            db_output_params={"semantic_indexing_enabled": False},
        )
        session.commit()

        assert result.consolidated_domain_keys == ()
        article = session.get(SubstrateArticle, result.article_id)
        assert article is not None
        assert article.text == "Story body text."


def test_run_db_output_persists_custom_records_without_extract_nodes() -> None:
    engine = _engine()
    env = {
        "BACKFIELD_PROJECT_ID": "1",
        "BACKFIELD_GRAPH_ID": "graph-custom-db",
        "BACKFIELD_RUN_ID": "run-custom-db",
    }
    consolidated = {
        "text": "Story body text.",
        "headline": "Headline",
        "url": "https://example.com/custom-db",
        "custom_records": _sample_custom_records(),
    }

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-custom-db",
            project_slug="proj-custom-db",
        )
        session.add(AgateRun(id="run-custom-db", graph_id="graph-custom-db", status="pending"))
        session.commit()
        env["BACKFIELD_PROJECT_ID"] = str(project_id)

    with patch.dict(os.environ, env, clear=False):
        with patch("backfield_db.session.get_engine", return_value=engine):
            out = run_db_output(
                {"semantic_indexing_enabled": False},
                {"data": consolidated},
            )

    assert out["success"] is True
    assert out["custom_records_persist"]["status"] == "succeeded"
    assert out["custom_records_persist"]["persisted"] is True
    assert out["custom_records_persist"]["count"] == 1

    with Session(engine) as session:
        row = session.exec(
            select(SubstrateCustomRecord).where(
                SubstrateCustomRecord.article_id == out["article_id"],
                SubstrateCustomRecord.record_type == "ingredients",
            )
        ).one()
        assert row.fields_json["item"] == "flour"
        assert row.source_run_id == "run-custom-db"
