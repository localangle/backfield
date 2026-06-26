"""Tests for public article metadata discovery queries."""

from __future__ import annotations

from datetime import date

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstrateArticleMeta,
)
from backfield_entities.public.article_metadata import (
    get_public_article_metadata,
    list_public_article_meta_types,
    list_public_article_meta_values,
)
from sqlmodel import Session, SQLModel, create_engine


def _seed_article_with_metadata(session: Session) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug="org-public-metadata")
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
        pub_date=date(2024, 1, 10),
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    article_id = int(article.id)  # type: ignore[arg-type]

    session.add(
        SubstrateArticleMeta(
            article_id=article_id,
            meta_type="topic",
            category="local_government_politics",
            rationale="test",
            confidence=0.9,
        )
    )
    session.add(
        SubstrateArticleMeta(
            article_id=article_id,
            meta_type="format",
            category="news_story",
            rationale="test",
            confidence=0.85,
        )
    )
    session.commit()
    return project_id, article_id


def test_list_public_article_meta_types() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, _article_id = _seed_article_with_metadata(session)
        result = list_public_article_meta_types(session, project_id=project_id)

    assert result.meta_types == ["format", "topic"]


def test_list_public_article_meta_values() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, _article_id = _seed_article_with_metadata(session)
        result = list_public_article_meta_values(
            session,
            project_id=project_id,
            meta_type="topic",
        )

    assert result.meta_type == "topic"
    assert result.values == ["local_government_politics"]


def test_list_public_article_meta_values_empty_for_unknown_type() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, _article_id = _seed_article_with_metadata(session)
        result = list_public_article_meta_values(
            session,
            project_id=project_id,
            meta_type="subject",
        )

    assert result.meta_type == "subject"
    assert result.values == []


def test_get_public_article_metadata() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, article_id = _seed_article_with_metadata(session)
        result = get_public_article_metadata(
            session,
            project_id=project_id,
            article_id=article_id,
        )

    assert result is not None
    assert result.article_id == article_id
    assert result.meta_types == ["format", "topic"]
    assert len(result.metadata) == 2
    assert {row.meta_type for row in result.metadata} == {"format", "topic"}


def test_get_public_article_metadata_missing_article() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, _article_id = _seed_article_with_metadata(session)
        result = get_public_article_metadata(
            session,
            project_id=project_id,
            article_id=99999,
        )

    assert result is None
