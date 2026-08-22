"""DBOutput persistence when only article body is present (Input → Backfield Output)."""

from __future__ import annotations

import pytest
from backfield_db import AgateRun, SubstrateArticle
from sqlmodel import Session, SQLModel, create_engine
from worker.substrate import persist_from_consolidated

from tests.worker.test_substrate_persistence import _bootstrap_project


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def test_persist_from_consolidated_accepts_article_body_only() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-article-only",
            project_slug="proj-article-only",
        )
        session.add(
            AgateRun(id="run-article-only", graph_id="graph-article-only", status="pending")
        )
        session.commit()

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-article-only",
            run_id="run-article-only",
            consolidated={
                "text": "Story body text.",
                "headline": "Headline",
                "url": "https://example.com/article-only",
            },
            db_output_params={"semantic_indexing_enabled": False},
        )
        session.commit()

        assert result.consolidated_domain_keys == ()
        assert result.reconciliation_summary.domain == "article"
        article = session.get(SubstrateArticle, result.article_id)
        assert article is not None
        assert article.text == "Story body text."
        assert article.headline == "Headline"


def test_persist_from_consolidated_accepts_article_body_via_alias() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-article-alias",
            project_slug="proj-article-alias",
        )
        session.add(
            AgateRun(id="run-article-alias", graph_id="graph-article-alias", status="pending")
        )
        session.commit()

        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-article-alias",
            run_id="run-article-alias",
            consolidated={
                "article_text": "The longer body used for extraction and persist.",
                "headline": "Events",
                "url": "https://example.com/article-alias",
            },
            db_output_params={"semantic_indexing_enabled": False},
        )
        session.commit()

        article = session.get(SubstrateArticle, result.article_id)
        assert article is not None
        assert article.text == "The longer body used for extraction and persist."


def test_persist_from_consolidated_rejects_empty_body_without_domains() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-article-empty",
            project_slug="proj-article-empty",
        )
        session.add(
            AgateRun(id="run-article-empty", graph_id="graph-article-empty", status="pending")
        )
        session.commit()

        with pytest.raises(RuntimeError, match="non-empty article body"):
            persist_from_consolidated(
                session,
                project_id=project_id,
                graph_id="graph-article-empty",
                run_id="run-article-empty",
                consolidated={
                    "text": "   ",
                    "headline": "Headline only",
                    "url": "https://example.com/article-empty",
                },
                db_output_params={"semantic_indexing_enabled": False},
            )
