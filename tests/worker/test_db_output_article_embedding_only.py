"""DBOutput persistence when only article_embedding is present (no extract nodes)."""

from __future__ import annotations

import os
from unittest.mock import patch

from backfield_db import (
    AgateRun,
    SubstrateArticle,
    SubstrateArticleEmbedding,
)
from sqlmodel import Session, SQLModel, create_engine, select
from worker.nodes.db_output import run_db_output
from worker.substrate import persist_from_consolidated

from tests.worker.test_substrate_persistence import _bootstrap_project


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _sample_embedding_block() -> dict:
    return {
        "embedded_text": "Headline\n\nStory body text.",
        "embedding": [0.1, 0.2, 0.3],
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 3,
    }


def test_persist_from_consolidated_accepts_article_embedding_only() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-embed-only",
            project_slug="proj-embed-only",
        )
        session.add(AgateRun(id="run-embed-only", graph_id="graph-embed-only", status="pending"))
        session.commit()

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-embed-only",
            run_id="run-embed-only",
            consolidated={
                "text": "Story body text.",
                "headline": "Headline",
                "url": "https://example.com/embed-only",
                "article_embedding": _sample_embedding_block(),
            },
            db_output_params={"semantic_indexing_enabled": False},
        )
        session.commit()

        assert result.consolidated_domain_keys == ()
        assert result.reconciliation_summary.domain == "article"
        article = session.get(SubstrateArticle, result.article_id)
        assert article is not None
        assert article.text == "Story body text."


def test_run_db_output_persists_article_embedding_without_extract_nodes() -> None:
    engine = _engine()
    env = {
        "BACKFIELD_PROJECT_ID": "1",
        "BACKFIELD_GRAPH_ID": "graph-embed-db",
        "BACKFIELD_RUN_ID": "run-embed-db",
    }
    consolidated = {
        "text": "Story body text.",
        "headline": "Headline",
        "url": "https://example.com/embed-db",
        "article_embedding": _sample_embedding_block(),
    }

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-embed-db",
            project_slug="proj-embed-db",
        )
        session.add(AgateRun(id="run-embed-db", graph_id="graph-embed-db", status="pending"))
        session.commit()
        env["BACKFIELD_PROJECT_ID"] = str(project_id)

    with patch.dict(os.environ, env, clear=False):
        with patch("backfield_db.session.get_engine", return_value=engine):
            out = run_db_output(
                {"semantic_indexing_enabled": False},
                {"data": consolidated},
            )

    assert out["success"] is True
    assert out["article_embedding_persist"]["status"] == "succeeded"
    assert out["article_embedding_persist"]["persisted"] is True

    with Session(engine) as session:
        row = session.exec(
            select(SubstrateArticleEmbedding).where(
                SubstrateArticleEmbedding.article_id == out["article_id"]
            )
        ).one()
        assert row.embedding_model == "text-embedding-3-small"
        assert row.embedding_dimensions == 3
