"""DBOutput persistence when only article_metadata is present (no extract nodes)."""

from __future__ import annotations

import os
from unittest.mock import patch

from backfield_db import (
    AgateRun,
    SubstrateArticle,
    SubstrateArticleMeta,
)
from sqlmodel import Session, SQLModel, create_engine, select
from worker.nodes.db_output import run_db_output
from worker.substrate import persist_from_consolidated

from tests.worker.test_substrate_persistence import _bootstrap_project


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _sample_metadata_block() -> dict:
    return {
        "meta_type": "subject",
        "subject": "development_project",
        "category": "development_project",
        "rationale": "The story focuses on a neighborhood zoning decision.",
        "confidence": 0.86,
        "prompt_preset": "subject",
    }


def test_persist_from_consolidated_accepts_article_metadata_only() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-meta-only",
            project_slug="proj-meta-only",
        )
        session.add(AgateRun(id="run-meta-only", graph_id="graph-meta-only", status="pending"))
        session.commit()

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-meta-only",
            run_id="run-meta-only",
            consolidated={
                "text": "Story body text.",
                "headline": "Headline",
                "url": "https://example.com/meta-only",
                "article_metadata": _sample_metadata_block(),
            },
            db_output_params={"semantic_indexing_enabled": False},
        )
        session.commit()

        assert result.consolidated_domain_keys == ()
        assert result.reconciliation_summary.domain == "article"
        article = session.get(SubstrateArticle, result.article_id)
        assert article is not None
        assert article.text == "Story body text."


def test_run_db_output_persists_article_metadata_without_extract_nodes() -> None:
    engine = _engine()
    env = {
        "BACKFIELD_PROJECT_ID": "1",
        "BACKFIELD_GRAPH_ID": "graph-meta-db",
        "BACKFIELD_RUN_ID": "run-meta-db",
    }
    consolidated = {
        "text": "Story body text.",
        "headline": "Headline",
        "url": "https://example.com/meta-db",
        "article_metadata": _sample_metadata_block(),
    }

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-meta-db",
            project_slug="proj-meta-db",
        )
        session.add(AgateRun(id="run-meta-db", graph_id="graph-meta-db", status="pending"))
        session.commit()
        env["BACKFIELD_PROJECT_ID"] = str(project_id)

    with patch.dict(os.environ, env, clear=False):
        with patch("backfield_db.session.get_engine", return_value=engine):
            out = run_db_output(
                {"semantic_indexing_enabled": False},
                {"data": consolidated},
            )

    assert out["success"] is True
    assert out["article_metadata_persist"]["status"] == "succeeded"
    assert out["article_metadata_persist"]["persisted"] is True

    with Session(engine) as session:
        row = session.exec(
            select(SubstrateArticleMeta).where(
                SubstrateArticleMeta.article_id == out["article_id"],
                SubstrateArticleMeta.meta_type == "subject",
            )
        ).one()
        assert row.category == "development_project"
        assert row.source_run_id == "run-meta-db"
