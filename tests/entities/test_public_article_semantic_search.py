"""Tests for public semantic article search."""

from __future__ import annotations

import json
from datetime import date

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
)
from backfield_db.article_embedding_models import SubstrateArticleEmbedding
from backfield_entities.public.article_semantic_search import (
    PublicArticleSemanticSearchParams,
    search_public_articles_semantic,
)
from sqlmodel import Session, SQLModel, create_engine


def _seed_project_with_embeddings(session: Session) -> tuple[int, str, str]:
    org = BackfieldOrganization(name="Org", slug="org-public-semantic-articles")
    session.add(org)
    session.commit()
    session.refresh(org)
    proj = BackfieldProject(
        name="News",
        slug="news",
        organization_id=int(org.id),  # type: ignore[arg-type]
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    project_id = int(proj.id)  # type: ignore[arg-type]
    config_id = "cfg-embed-1"
    provider_model_id = "text-embedding-3-small"

    article_a = SubstrateArticle(
        project_id=project_id,
        headline="Bridge repair funding",
        text="City council approved money for the downtown bridge.",
        pub_date=date(2024, 3, 1),
    )
    article_b = SubstrateArticle(
        project_id=project_id,
        headline="School lunch menu",
        text="Students will see new vegetarian options this fall.",
        pub_date=date(2024, 2, 1),
    )
    session.add(article_a)
    session.add(article_b)
    session.commit()
    session.refresh(article_a)
    session.refresh(article_b)

    session.add(
        SubstrateArticleEmbedding(
            article_id=int(article_a.id),  # type: ignore[arg-type]
            embedded_text="bridge story",
            embedding_model=provider_model_id,
            embedding_dimensions=2,
            embedding_ai_model_config_id=config_id,
            embedding=json.dumps([1.0, 0.0]),
        )
    )
    session.add(
        SubstrateArticleEmbedding(
            article_id=int(article_b.id),  # type: ignore[arg-type]
            embedded_text="school story",
            embedding_model=provider_model_id,
            embedding_dimensions=2,
            embedding_ai_model_config_id=config_id,
            embedding=json.dumps([0.0, 1.0]),
        )
    )
    session.commit()
    return project_id, config_id, provider_model_id


def test_search_public_articles_semantic_orders_by_score() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, config_id, provider_model_id = _seed_project_with_embeddings(session)

        items, total = search_public_articles_semantic(
            session,
            project_id=project_id,
            query_vector=[1.0, 0.0],
            embedding_model_config_id=config_id,
            embedding_provider_model_id=provider_model_id,
            params=PublicArticleSemanticSearchParams(),
        )

    assert total == 2
    assert len(items) == 2
    assert items[0].headline == "Bridge repair funding"
    assert items[0].score >= items[1].score


def test_search_public_articles_semantic_skips_articles_without_embeddings() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, config_id, provider_model_id = _seed_project_with_embeddings(session)
        session.add(
            SubstrateArticle(
                project_id=project_id,
                headline="No embedding yet",
                text="This story has no vector row.",
            )
        )
        session.commit()

        items, total = search_public_articles_semantic(
            session,
            project_id=project_id,
            query_vector=[1.0, 0.0],
            embedding_model_config_id=config_id,
            embedding_provider_model_id=provider_model_id,
            params=PublicArticleSemanticSearchParams(),
        )

    assert total == 2
    assert all(item.headline != "No embedding yet" for item in items)
