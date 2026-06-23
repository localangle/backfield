"""Article queries and serializers for the public API."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from urllib.parse import urlparse

from backfield_db import (
    SubstrateArticle,
    SubstrateArticleMeta,
    SubstrateLocationMention,
    SubstrateOrganizationMention,
    SubstratePersonMention,
)
from pydantic import BaseModel, Field
from sqlalchemy import func, literal, or_
from sqlmodel import Session, col, select

from backfield_entities.public.article_hub import (
    PublicArticleCountsOut,
    PublicArticleImageOut,
)
from backfield_entities.public.keyword_query import article_keyword_tsquery

PUBLIC_ARTICLE_PREVIEW_MAX_LEN = 280
_INTERNAL_ARTICLE_SOURCE_ID = "backfield_text_fingerprint"


class PublicArticleMetaOut(BaseModel):
    meta_type: str
    category: str
    confidence: float


class PublicArticleSourceOut(BaseModel):
    id: str
    name: str


class PublicArticleOut(BaseModel):
    id: int
    headline: str
    url: str | None = None
    author: str | None = None
    pub_date: date | None = None
    source: PublicArticleSourceOut | None = None
    preview: str | None = None
    metadata: list[PublicArticleMetaOut] = Field(default_factory=list)
    embedded: bool | None = None
    counts: PublicArticleCountsOut | None = None
    images: list[PublicArticleImageOut] | None = None


@dataclass(frozen=True)
class ArticleMetaClause:
    meta_type: str
    categories: tuple[str, ...] = ()
    negate: bool = False


@dataclass(frozen=True)
class PublicArticleSearchParams:
    q: str | None = None
    meta_type: str | None = None
    meta_category: str | None = None
    exclude_meta_type: str | None = None
    exclude_meta_category: str | None = None
    section: str | None = None
    meta_clauses: tuple[ArticleMetaClause, ...] = ()
    author: str | None = None
    external_source: str | None = None
    has_mentions: str | None = None
    pub_date_from: date | None = None
    pub_date_to: date | None = None
    limit: int = 25
    offset: int = 0


def article_preview(text: str, *, max_len: int = PUBLIC_ARTICLE_PREVIEW_MAX_LEN) -> str:
    stripped = text.strip()
    if len(stripped) <= max_len:
        return stripped
    if max_len <= 1:
        return "…"
    return f"{stripped[: max_len - 1]}…"


def _meta_rows_for_articles(
    session: Session, article_ids: list[int]
) -> dict[int, list[PublicArticleMetaOut]]:
    if not article_ids:
        return {}
    rows = session.exec(
        select(SubstrateArticleMeta)
        .where(col(SubstrateArticleMeta.article_id).in_(article_ids))
        .order_by(
            col(SubstrateArticleMeta.article_id),
            col(SubstrateArticleMeta.meta_type),
            col(SubstrateArticleMeta.id),
        )
    ).all()
    out: dict[int, list[PublicArticleMetaOut]] = {aid: [] for aid in article_ids}
    for row in rows:
        aid = int(row.article_id)
        out.setdefault(aid, []).append(
            PublicArticleMetaOut(
                meta_type=row.meta_type,
                category=row.category,
                confidence=float(row.confidence),
            )
        )
    return out


def article_public_source(
    *,
    external_source: str | None,
    url: str | None,
) -> PublicArticleSourceOut | None:
    source_id = (external_source or "").strip()
    if source_id and source_id != _INTERNAL_ARTICLE_SOURCE_ID:
        return PublicArticleSourceOut(id=source_id, name=source_id)
    if url and url.strip():
        parsed = urlparse(url.strip())
        hostname = parsed.hostname or ""
        if hostname:
            host = hostname.removeprefix("www.")
            return PublicArticleSourceOut(id=host, name=host)
    return None


def resolve_public_article_search_params(
    params: PublicArticleSearchParams,
) -> PublicArticleSearchParams:
    """Apply search sugar such as ``section`` → topic metadata filter."""
    section_value = (params.section or "").strip()
    if not section_value:
        return params
    return replace(
        params,
        section=None,
        meta_type="topic",
        meta_category=section_value,
    )


def _article_to_public_out(
    article: SubstrateArticle,
    *,
    metadata: list[PublicArticleMetaOut],
) -> PublicArticleOut:
    preview = article_preview(article.text)
    source = article_public_source(
        external_source=article.external_source,
        url=article.url,
    )
    return PublicArticleOut(
        id=int(article.id),  # type: ignore[arg-type]
        headline=article.headline,
        url=article.url,
        author=article.author,
        pub_date=article.pub_date,
        source=source,
        preview=preview,
        metadata=metadata,
    )


def _active_articles_for_project(session: Session, project_id: int):
    return select(SubstrateArticle).where(
        SubstrateArticle.project_id == project_id,
        SubstrateArticle.deleted == False,  # noqa: E712
    )


def _article_fulltext_vector():
    """Expression matching ``idx_substrate_article_fulltext`` for index-backed search."""
    empty = literal("")
    space = literal(" ")
    document = (
        func.coalesce(SubstrateArticle.headline, empty)
        .op("||")(space)
        .op("||")(func.coalesce(SubstrateArticle.text, empty))
        .op("||")(space)
        .op("||")(func.coalesce(SubstrateArticle.url, empty))
    )
    return func.to_tsvector("english", document)


def _apply_public_article_keyword_filter(
    stmt,
    q: str,
    session: Session,
):
    """Keyword match on headline, body text, and URL.

    PostgreSQL uses full-text search (``websearch_to_tsquery``) with optional rank
    for ordering. Supports quoted phrases, ``OR``, and ``-`` exclusions in ``q``.
    Other dialects fall back to case-insensitive substring match on the full string.
    """
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        vector = _article_fulltext_vector()
        ts_query = article_keyword_tsquery(q)
        rank = func.ts_rank_cd(vector, ts_query)
        return stmt.where(vector.op("@@")(ts_query)), rank

    pattern = f"%{q}%"
    return (
        stmt.where(
            or_(
                SubstrateArticle.headline.ilike(pattern),
                SubstrateArticle.url.ilike(pattern),
                SubstrateArticle.text.ilike(pattern),
            )
        ),
        None,
    )


def _apply_public_article_list_filters(
    stmt,
    *,
    meta_type: str | None,
    meta_category: str | None,
    exclude_meta_type: str | None = None,
    exclude_meta_category: str | None = None,
    meta_clauses: tuple[ArticleMetaClause, ...] = (),
    author: str | None = None,
    external_source: str | None = None,
    has_mentions: str | None = None,
    pub_date_from: date | None,
    pub_date_to: date | None,
):
    if pub_date_from is not None:
        stmt = stmt.where(col(SubstrateArticle.pub_date) >= pub_date_from)
    if pub_date_to is not None:
        stmt = stmt.where(col(SubstrateArticle.pub_date) <= pub_date_to)

    author_value = (author or "").strip()
    if author_value:
        stmt = stmt.where(func.lower(SubstrateArticle.author) == author_value.lower())

    external_source_value = (external_source or "").strip()
    if external_source_value:
        stmt = stmt.where(
            func.lower(SubstrateArticle.external_source) == external_source_value.lower()
        )

    has_mentions_value = (has_mentions or "").strip().lower()
    if has_mentions_value == "place":
        has_mentions_value = "location"
    if has_mentions_value == "location":
        mention_stmt = select(SubstrateLocationMention.article_id).where(
            SubstrateLocationMention.deleted == False  # noqa: E712
        )
        stmt = stmt.where(col(SubstrateArticle.id).in_(mention_stmt))
    elif has_mentions_value == "person":
        mention_stmt = select(SubstratePersonMention.article_id).where(
            SubstratePersonMention.deleted == False  # noqa: E712
        )
        stmt = stmt.where(col(SubstrateArticle.id).in_(mention_stmt))
    elif has_mentions_value == "organization":
        mention_stmt = select(SubstrateOrganizationMention.article_id).where(
            SubstrateOrganizationMention.deleted == False  # noqa: E712
        )
        stmt = stmt.where(col(SubstrateArticle.id).in_(mention_stmt))

    meta_type_value = (meta_type or "").strip()
    if meta_type_value:
        meta_stmt = select(SubstrateArticleMeta.article_id).where(
            SubstrateArticleMeta.meta_type == meta_type_value
        )
        meta_category_value = (meta_category or "").strip()
        if meta_category_value:
            meta_stmt = meta_stmt.where(SubstrateArticleMeta.category == meta_category_value)
        stmt = stmt.where(col(SubstrateArticle.id).in_(meta_stmt))

    exclude_meta_type_value = (exclude_meta_type or "").strip()
    if exclude_meta_type_value:
        exclude_stmt = select(SubstrateArticleMeta.article_id).where(
            SubstrateArticleMeta.meta_type == exclude_meta_type_value
        )
        exclude_meta_category_value = (exclude_meta_category or "").strip()
        if exclude_meta_category_value:
            exclude_stmt = exclude_stmt.where(
                SubstrateArticleMeta.category == exclude_meta_category_value
            )
        stmt = stmt.where(~col(SubstrateArticle.id).in_(exclude_stmt))

    for clause in meta_clauses:
        meta_stmt = select(SubstrateArticleMeta.article_id).where(
            SubstrateArticleMeta.meta_type == clause.meta_type
        )
        if clause.categories:
            meta_stmt = meta_stmt.where(col(SubstrateArticleMeta.category).in_(clause.categories))
        if clause.negate:
            stmt = stmt.where(~col(SubstrateArticle.id).in_(meta_stmt))
        else:
            stmt = stmt.where(col(SubstrateArticle.id).in_(meta_stmt))

    return stmt


def search_public_articles(
    session: Session,
    *,
    project_id: int,
    params: PublicArticleSearchParams,
) -> tuple[list[PublicArticleOut], int]:
    params = resolve_public_article_search_params(params)
    stmt = _active_articles_for_project(session, project_id)

    rank_expr = None
    q = (params.q or "").strip()
    if q:
        stmt, rank_expr = _apply_public_article_keyword_filter(stmt, q, session)

    stmt = _apply_public_article_list_filters(
        stmt,
        meta_type=params.meta_type,
        meta_category=params.meta_category,
        exclude_meta_type=params.exclude_meta_type,
        exclude_meta_category=params.exclude_meta_category,
        meta_clauses=params.meta_clauses,
        author=params.author,
        external_source=params.external_source,
        has_mentions=params.has_mentions,
        pub_date_from=params.pub_date_from,
        pub_date_to=params.pub_date_to,
    )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(session.exec(count_stmt).one())

    order_by: list = []
    if rank_expr is not None:
        order_by.append(rank_expr.desc())
    order_by.extend(
        [
            col(SubstrateArticle.pub_date).desc().nulls_last(),
            col(SubstrateArticle.id).desc(),
        ]
    )
    stmt = stmt.order_by(*order_by).limit(params.limit).offset(params.offset)

    articles = list(session.exec(stmt).all())
    article_ids = [int(a.id) for a in articles if a.id is not None]
    meta_by_id = _meta_rows_for_articles(session, article_ids)

    items = [
        _article_to_public_out(
            article,
            metadata=meta_by_id.get(int(article.id), []),  # type: ignore[arg-type]
        )
        for article in articles
    ]
    return items, total


def get_public_article(
    session: Session,
    *,
    project_id: int,
    article_id: int,
) -> PublicArticleOut | None:
    article = session.exec(
        select(SubstrateArticle).where(
            SubstrateArticle.id == article_id,
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
        )
    ).first()
    if article is None or article.id is None:
        return None
    meta_by_id = _meta_rows_for_articles(session, [int(article.id)])
    return _article_to_public_out(
        article,
        metadata=meta_by_id.get(int(article.id), []),
    )
