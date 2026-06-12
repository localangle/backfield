"""Tests for image embedding DBOutput persistence."""

from __future__ import annotations

from backfield_db import SubstrateImage, SubstrateImageEmbedding
from backfield_entities.ingest.image_embedding.persist import (
    persist_image_embeddings_after_db_output,
)
from sqlmodel import Session, SQLModel, create_engine, select

from tests.worker.test_substrate_persistence import _bootstrap_project


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _sample_image_embedding_block() -> dict:
    return {
        "id": "hero",
        "url": "https://example.com/hero.jpg",
        "caption": "Hero image",
        "generated_text": "A storefront with a red awning.",
        "embedding": [0.1, 0.2, 0.3],
        "embedding_model": "text-embedding-3-small",
        "embedding_dimensions": 3,
        "description_model": "gpt-4o-mini",
    }


def test_persist_image_embeddings_creates_substrate_rows() -> None:
    engine = _engine()
    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-img-embed",
            project_slug="proj-img-embed",
        )
        from backfield_db import SubstrateArticle

        article = SubstrateArticle(
            project_id=project_id,
            text="Story body.",
            headline="Headline",
            url="https://example.com/story",
        )
        session.add(article)
        session.commit()
        session.refresh(article)
        assert article.id is not None

        summary = persist_image_embeddings_after_db_output(
            session,
            article_id=article.id,
            consolidated={"image_embeddings": [_sample_image_embedding_block()]},
            policy="smart_merge",
        )
        session.commit()

        assert summary["status"] == "succeeded"
        assert summary["persisted"] is True
        assert summary["count"] == 1

        image_row = session.exec(
            select(SubstrateImage).where(SubstrateImage.article_id == article.id)
        ).one()
        assert image_row.image_id == "hero"

        embedding_row = session.exec(
            select(SubstrateImageEmbedding).where(
                SubstrateImageEmbedding.substrate_image_id == image_row.id
            )
        ).one()
        assert embedding_row.generated_text == "A storefront with a red awning."
        assert embedding_row.embedding_model == "text-embedding-3-small"
