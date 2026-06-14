"""Tests for public article facet queries."""

from __future__ import annotations

from datetime import date

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstrateArticleMeta,
)
from backfield_entities.public.article_facets import get_public_article_facets
from sqlmodel import Session, SQLModel, create_engine


def test_get_public_article_facets_returns_distinct_values() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-public-facets")
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

        article = SubstrateArticle(
            project_id=project_id,
            headline="Budget vote",
            text="Body",
            author="Jane Doe",
            external_source="Daily Herald",
            pub_date=date(2024, 1, 10),
        )
        session.add(article)
        session.commit()
        session.refresh(article)

        session.add(
            SubstrateArticleMeta(
                article_id=int(article.id),  # type: ignore[arg-type]
                meta_type="subject",
                category="local_government_politics",
                rationale="test",
                confidence=0.9,
            )
        )
        session.add(
            SubstrateArticleMeta(
                article_id=int(article.id),  # type: ignore[arg-type]
                meta_type="format",
                category="news_story",
                rationale="test",
                confidence=0.9,
            )
        )
        session.commit()

        facets = get_public_article_facets(session, project_id=project_id)

    assert facets.authors == ["Jane Doe"]
    assert facets.external_sources == ["Daily Herald"]
    assert facets.subject_categories == ["local_government_politics"]
    assert facets.format_categories == ["news_story"]
