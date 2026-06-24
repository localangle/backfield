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
    ArticleMetaClause,
    PublicArticleSearchParams,
    article_preview,
    article_public_source,
    get_public_article,
    search_public_articles,
)
from sqlmodel import Session, SQLModel, create_engine


def test_article_preview_truncates_long_text() -> None:
    long_text = "word " * 200
    preview = article_preview(long_text)
    assert len(preview) <= PUBLIC_ARTICLE_PREVIEW_MAX_LEN
    assert preview.endswith("…")


def test_article_public_source_prefers_publication_id() -> None:
    source = article_public_source(
        external_source="Chicago Sun-Times",
        url="https://chicago.suntimes.com/story",
    )
    assert source is not None
    assert source.id == "Chicago Sun-Times"
    assert source.name == "Chicago Sun-Times"


def test_article_public_source_uses_url_host_when_no_publication() -> None:
    source = article_public_source(
        external_source=None,
        url="https://www.example.com/budget",
    )
    assert source is not None
    assert source.id == "example.com"
    assert source.name == "example.com"


def test_article_public_source_hides_internal_fingerprint() -> None:
    assert (
        article_public_source(
            external_source="backfield_text_fingerprint",
            url=None,
        )
        is None
    )


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
                meta_type="topic",
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
                meta_type="topic",
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
        assert detail.text is None
        assert detail.metadata[0].meta_type == "topic"

        detail_with_text = get_public_article(
            session,
            project_id=project_id,
            article_id=int(a1.id),  # type: ignore[arg-type]
            include_text=True,
        )
        assert detail_with_text is not None
        assert detail_with_text.preview == "Body one"
        assert detail_with_text.text == "Body one"


def test_search_public_articles_excludes_metadata() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-public-articles-exclude")
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

        included = SubstrateArticle(
            project_id=project_id,
            headline="Local politics",
            text="Body one",
            pub_date=date(2024, 1, 10),
        )
        excluded = SubstrateArticle(
            project_id=project_id,
            headline="Sports roundup",
            text="Body two",
            pub_date=date(2024, 1, 11),
        )
        session.add(included)
        session.add(excluded)
        session.commit()
        session.refresh(included)
        session.refresh(excluded)

        session.add(
            SubstrateArticleMeta(
                article_id=int(included.id),  # type: ignore[arg-type]
                meta_type="topic",
                category="local_government_politics",
                rationale="test",
                confidence=0.9,
            )
        )
        session.add(
            SubstrateArticleMeta(
                article_id=int(excluded.id),  # type: ignore[arg-type]
                meta_type="topic",
                category="sports",
                rationale="test",
                confidence=0.9,
            )
        )
        session.commit()

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(
                meta_type="topic",
                exclude_meta_type="topic",
                exclude_meta_category="sports",
            ),
        )
        assert total == 1
        assert items[0].headline == "Local politics"

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(exclude_meta_type="topic"),
        )
        assert total == 0
        assert items == []


def test_search_public_articles_filters_author_section_and_mentions() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-public-search-filters")
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
            url="https://www.dailyherald.com/budget",
            pub_date=date(2024, 1, 10),
        )
        session.add(article)
        session.commit()
        session.refresh(article)

        session.add(
            SubstrateArticleMeta(
                article_id=int(article.id),  # type: ignore[arg-type]
                meta_type="topic",
                category="local_government_politics",
                rationale="test",
                confidence=0.9,
            )
        )
        session.commit()

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(author="Jane Doe"),
        )
        assert total == 1
        assert items[0].source is not None
        assert items[0].source.id == "Daily Herald"
        assert items[0].source.name == "Daily Herald"
        assert items[0].metadata[0].category == "local_government_politics"

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(section="local_government_politics"),
        )
        assert total == 1
        assert items[0].headline == "Budget vote"

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(external_source="Daily Herald"),
        )
        assert total == 1

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(has_mentions="location"),
        )
        assert total == 0


def test_search_public_articles_meta_clauses() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-meta-clauses")
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

        def add_article(headline: str, meta_rows: list[tuple[str, str]]) -> SubstrateArticle:
            article = SubstrateArticle(
                project_id=project_id,
                headline=headline,
                text="Body",
                pub_date=date(2024, 1, 10),
            )
            session.add(article)
            session.commit()
            session.refresh(article)
            for meta_type, category in meta_rows:
                session.add(
                    SubstrateArticleMeta(
                        article_id=int(article.id),  # type: ignore[arg-type]
                        meta_type=meta_type,
                        category=category,
                        rationale="test",
                        confidence=0.9,
                    )
                )
            session.commit()
            return article

        matching = add_article(
            "Pro sports evergreen story",
            [
                ("format", "news_story"),
                ("temporal_orientation", "evergreen"),
                ("topic", "pro_sports"),
            ],
        )
        add_article(
            "Pro sports backward story",
            [
                ("format", "news_story"),
                ("temporal_orientation", "backward"),
                ("topic", "pro_sports"),
            ],
        )
        add_article(
            "Sports obituary",
            [
                ("format", "news_story"),
                ("temporal_orientation", "evergreen"),
                ("topic", "obituaries"),
            ],
        )
        add_article(
            "Dual topic story",
            [
                ("topic", "pro_sports"),
                ("topic", "analysis"),
            ],
        )

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(
                meta_clauses=(
                    ArticleMetaClause(meta_type="format", categories=("news_story",)),
                    ArticleMetaClause(
                        meta_type="temporal_orientation",
                        categories=("backward", "evergreen"),
                    ),
                    ArticleMetaClause(meta_type="topic", categories=("pro_sports",)),
                    ArticleMetaClause(
                        meta_type="topic",
                        categories=("obituaries",),
                        negate=True,
                    ),
                ),
            ),
        )
        assert total == 2
        assert {item.headline for item in items} == {
            "Pro sports evergreen story",
            "Pro sports backward story",
        }

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(
                meta_clauses=(
                    ArticleMetaClause(meta_type="topic", categories=("pro_sports",)),
                    ArticleMetaClause(meta_type="topic", categories=("analysis",)),
                ),
            ),
        )
        assert total == 1
        assert items[0].headline == "Dual topic story"

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(
                meta_type="format",
                meta_category="news_story",
                meta_clauses=(
                    ArticleMetaClause(meta_type="topic", categories=("pro_sports",)),
                ),
            ),
        )
        assert total == 2
        assert int(matching.id) in {item.id for item in items}  # type: ignore[arg-type]

        items, total = search_public_articles(
            session,
            project_id=project_id,
            params=PublicArticleSearchParams(
                meta_clauses=(ArticleMetaClause(meta_type="format", categories=()),),
            ),
        )
        assert total == 3
