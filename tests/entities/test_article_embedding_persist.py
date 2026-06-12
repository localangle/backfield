"""Tests for article embedding DBOutput persist."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
)
from backfield_db.article_embedding_models import SubstrateArticleEmbedding
from backfield_entities.ingest.article_embedding.persist import (
    persist_article_embedding_after_db_output,
)
from sqlmodel import Session, SQLModel, create_engine, select


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _seed_article(session: Session) -> int:
    org = BackfieldOrganization(name="Org", slug="org-article-embed")
    session.add(org)
    session.commit()
    session.refresh(org)
    proj = BackfieldProject(
        name="Demo",
        slug="demo-article-embed",
        organization_id=int(org.id),  # type: ignore[arg-type]
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    article = SubstrateArticle(
        project_id=int(proj.id),  # type: ignore[arg-type]
        headline="Headline",
        text="Body",
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    return int(article.id)  # type: ignore[arg-type]


def _sample_block() -> dict:
    return {
        "embedded_text": "Headline\n\nBody",
        "embedding": [0.1, 0.2, 0.3],
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 3,
        "embedding_ai_model_config_id": "cfg-1",
    }


def test_persist_creates_row() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        summary = persist_article_embedding_after_db_output(
            session,
            article_id=article_id,
            consolidated={"article_embedding": _sample_block()},
            policy="smart_merge",
        )
        assert summary["status"] == "succeeded"
        assert summary["persisted"] is True
        row = session.exec(
            select(SubstrateArticleEmbedding).where(
                SubstrateArticleEmbedding.article_id == article_id
            )
        ).one()
        assert row.embedding_model == "text-embedding-3-small"
        assert row.embedding_dimensions == 3


def test_add_only_skips_existing() -> None:
    engine = _engine()
    with Session(engine) as session:
        article_id = _seed_article(session)
        persist_article_embedding_after_db_output(
            session,
            article_id=article_id,
            consolidated={"article_embedding": _sample_block()},
            policy="smart_merge",
        )
        summary = persist_article_embedding_after_db_output(
            session,
            article_id=article_id,
            consolidated={
                "article_embedding": {
                    **_sample_block(),
                    "embedded_text": "Different body",
                    "embedding": [0.9, 0.8, 0.7],
                }
            },
            policy="add_only",
        )
        assert summary["status"] == "skipped"
        row = session.exec(
            select(SubstrateArticleEmbedding).where(
                SubstrateArticleEmbedding.article_id == article_id
            )
        ).one()
        assert row.embedded_text == "Headline\n\nBody"
