"""Tests for public article query helpers."""

from __future__ import annotations

from datetime import date

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstrateArticleMeta,
)
from backfield_entities.public.articles import (
    PUBLIC_ARTICLE_PREVIEW_MAX_LEN,
    PublicArticleSearchParams,
    article_preview,
    get_public_article,
    search_public_articles,
)
from sqlmodel import Session, SQLModel, create_engine


def test_article_preview_truncates_long_text() -> None:
    long_text = "word " * 200
    preview = article_preview(long_text)
    assert len(preview) <= PUBLIC_ARTICLE_PREVIEW_MAX_LEN
    assert preview.endswith("…")


def test_search_public_articles_matches_body_text() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-public-body-search")
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

        session.add(
            SubstrateArticle(
                project_id=project_id,
                headline="School board meeting",
                text="The auditorium renovation will begin next month.",
                pub_date=date(2024, 1, 10),
            )
        )
        session.add(
            SubstrateArticle(
                project_id=project_id,
                headline="Budget overview",
                text="Unrelated story body.",
                pub_date=date(2024, 1, 11),
            )
        )
        session.commit()

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(q="renovation"),
        )
        assert total == 1
        assert len(items) == 1
        assert items[0].headline == "School board meeting"


def test_search_public_articles_filters_metadata_and_dates() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-public-articles")
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

        a1 = SubstrateArticle(
            project_id=project_id,
            headline="Budget vote",
            text="Body one",
            pub_date=date(2024, 1, 10),
        )
        a2 = SubstrateArticle(
            project_id=project_id,
            headline="School board",
            text="Body two",
            pub_date=date(2024, 2, 10),
        )
        session.add(a1)
        session.add(a2)
        session.commit()
        session.refresh(a1)
        session.refresh(a2)

        session.add(
            SubstrateArticleMeta(
                article_id=int(a1.id),  # type: ignore[arg-type]
                meta_type="subject",
                category="local_government_politics",
                rationale="test",
                confidence=0.9,
            )
        )
        session.commit()

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(
                meta_type="subject",
                meta_category="local_government_politics",
                pub_date_from=date(2024, 1, 1),
                pub_date_to=date(2024, 1, 31),
            ),
        )
        assert total == 1
        assert len(items) == 1
        assert items[0].headline == "Budget vote"
        assert items[0].metadata[0].category == "local_government_politics"

        detail = get_public_article(
            session,
            project_id=project_id,
            article_id=int(a1.id),  # type: ignore[arg-type]
        )
        assert detail is not None
        assert detail.preview == "Body one"
        assert detail.metadata[0].meta_type == "subject"
