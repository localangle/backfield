"""Tests for public article keyword search."""

from __future__ import annotations

import os
from datetime import date

import pytest
from backfield_db import BackfieldOrganization, BackfieldProject, SubstrateArticle
from backfield_entities.public.articles import (
    PublicArticleSearchParams,
    search_public_articles,
)
from backfield_entities.public.keyword_query import article_keyword_tsquery
from sqlalchemy import func
from sqlmodel import Session, SQLModel, create_engine, select

POSTGRES_TEST_URL = os.getenv("TEST_POSTGRES_URL", "").strip()


def _seed_sqlite_project(session: Session) -> int:
    org = BackfieldOrganization(name="Org", slug="org-kw")
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
    return int(proj.id)  # type: ignore[arg-type]


def test_article_keyword_tsquery_uses_websearch() -> None:
    expr = article_keyword_tsquery('"city council" OR mayor -sports')
    assert "websearch_to_tsquery" in str(expr)


def test_sqlite_keyword_search_matches_substring() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id = _seed_sqlite_project(session)
        session.add(
            SubstrateArticle(
                project_id=project_id,
                headline="City council votes on budget",
                text="The council approved the budget after a long debate downtown.",
                pub_date=date(2024, 3, 1),
            )
        )
        session.commit()

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(q="budget"),
        )

    assert total == 1
    assert items[0].headline == "City council votes on budget"


@pytest.fixture(scope="module")
def postgres_engine():
    if not POSTGRES_TEST_URL.startswith("postgresql"):
        pytest.skip("Set TEST_POSTGRES_URL to a PostgreSQL URL to run FTS keyword tests.")
    engine = create_engine(POSTGRES_TEST_URL)
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_postgres_phrase_search_requires_adjacency(postgres_engine) -> None:
    with Session(postgres_engine) as session:
        project_id = _seed_sqlite_project(session)
        session.add(
            SubstrateArticle(
                project_id=project_id,
                headline="Phrase match",
                text="The council approved the budget after a long debate downtown.",
                pub_date=date(2024, 3, 1),
            )
        )
        session.add(
            SubstrateArticle(
                project_id=project_id,
                headline="Split words",
                text="After a long day, the council held a separate debate downtown.",
                pub_date=date(2024, 3, 2),
            )
        )
        session.commit()

        phrase_items, phrase_total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(q='"long debate"'),
        )
        plain_items, plain_total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(q="long debate"),
        )

    assert phrase_total == 1
    assert phrase_items[0].headline == "Phrase match"
    assert plain_total == 2


def test_postgres_or_search(postgres_engine) -> None:
    with Session(postgres_engine) as session:
        project_id = _seed_sqlite_project(session)
        session.add(
            SubstrateArticle(
                project_id=project_id,
                headline="Budget story",
                text="The city budget passed unanimously.",
                pub_date=date(2024, 3, 1),
            )
        )
        session.add(
            SubstrateArticle(
                project_id=project_id,
                headline="Sports story",
                text="The home team won the championship game.",
                pub_date=date(2024, 3, 2),
            )
        )
        session.commit()

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(q="budget OR championship"),
        )

    assert total == 2
    headlines = {item.headline for item in items}
    assert headlines == {"Budget story", "Sports story"}


def test_postgres_exclude_search(postgres_engine) -> None:
    with Session(postgres_engine) as session:
        project_id = _seed_sqlite_project(session)
        session.add(
            SubstrateArticle(
                project_id=project_id,
                headline="Budget story",
                text="The city budget passed unanimously.",
                pub_date=date(2024, 3, 1),
            )
        )
        session.add(
            SubstrateArticle(
                project_id=project_id,
                headline="Budget sports",
                text="The city budget funded a new sports arena.",
                pub_date=date(2024, 3, 2),
            )
        )
        session.commit()

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(q="budget -sports"),
        )

    assert total == 1
    assert items[0].headline == "Budget story"


def test_postgres_websearch_to_tsquery_parses_phrase(postgres_engine) -> None:
    with Session(postgres_engine) as session:
        parsed = session.exec(
            select(func.websearch_to_tsquery("english", '"long debate"'))
        ).one()
    assert parsed is not None
