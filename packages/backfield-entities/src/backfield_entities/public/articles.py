"""Article queries and serializers for the public API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backfield_db import SubstrateArticle, SubstrateArticleMeta
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlmodel import Session, col, select

from backfield_entities.public.article_hub import PublicArticleCountsOut, article_hub_counts

PUBLIC_ARTICLE_PREVIEW_MAX_LEN = 280


class PublicArticleMetaOut(BaseModel):
    meta_type: str
    category: str
    confidence: float


class PublicArticleOut(BaseModel):
    id: int
    headline: str
    url: str | None = None
    author: str | None = None
    pub_date: date | None = None
    external_source: str | None = None
    external_id: str | None = None
    entry_id: str | None = None
    preview: str | None = None
    metadata: list[PublicArticleMetaOut] = Field(default_factory=list)
    counts: PublicArticleCountsOut | None = None


@dataclass(frozen=True)
class PublicArticleSearchParams:
    q: str | None = None
    meta_type: str | None = None
    meta_category: str | None = None
    pub_date_from: date | None = None
    pub_date_to: date | None = None
    limit: int = 25
    offset: int = 0
    include_preview: bool = False


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


def _article_to_public_out(
    article: SubstrateArticle,
    *,
    metadata: list[PublicArticleMetaOut],
    include_preview: bool,
    include_provenance: bool,
    counts: PublicArticleCountsOut | None = None,
) -> PublicArticleOut:
    preview = article_preview(article.text) if include_preview else None
    return PublicArticleOut(
        id=int(article.id),  # type: ignore[arg-type]
        headline=article.headline,
        url=article.url,
        author=article.author,
        pub_date=article.pub_date,
        external_source=article.external_source if include_provenance else None,
        external_id=article.external_id if include_provenance else None,
        entry_id=article.entry_id if include_provenance else None,
        preview=preview,
        metadata=metadata,
        counts=counts,
    )


def _active_articles_for_project(session: Session, project_id: int):
    return select(SubstrateArticle).where(
        SubstrateArticle.project_id == project_id,
        SubstrateArticle.deleted == False,  # noqa: E712
    )


def search_public_articles(
    session: Session,
    *,
    project_id: int,
    params: PublicArticleSearchParams,
) -> tuple[list[PublicArticleOut], int]:
    stmt = _active_articles_for_project(session, project_id)

    q = (params.q or "").strip()
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                SubstrateArticle.headline.ilike(pattern),
                SubstrateArticle.url.ilike(pattern),
            )
        )

    if params.pub_date_from is not None:
        stmt = stmt.where(col(SubstrateArticle.pub_date) >= params.pub_date_from)
    if params.pub_date_to is not None:
        stmt = stmt.where(col(SubstrateArticle.pub_date) <= params.pub_date_to)

    meta_type = (params.meta_type or "").strip()
    if meta_type:
        meta_stmt = select(SubstrateArticleMeta.article_id).where(
            SubstrateArticleMeta.meta_type == meta_type
        )
        meta_category = (params.meta_category or "").strip()
        if meta_category:
            meta_stmt = meta_stmt.where(SubstrateArticleMeta.category == meta_category)
        stmt = stmt.where(col(SubstrateArticle.id).in_(meta_stmt))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(session.exec(count_stmt).one())

    stmt = stmt.order_by(
        col(SubstrateArticle.pub_date).desc().nulls_last(),
        col(SubstrateArticle.id).desc(),
    ).limit(params.limit).offset(params.offset)

    articles = list(session.exec(stmt).all())
    article_ids = [int(a.id) for a in articles if a.id is not None]
    meta_by_id = _meta_rows_for_articles(session, article_ids)

    items = [
        _article_to_public_out(
            article,
            metadata=meta_by_id.get(int(article.id), []),  # type: ignore[arg-type]
            include_preview=params.include_preview,
            include_provenance=False,
        )
        for article in articles
    ]
    return items, total


def get_public_article(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    include_preview: bool = True,
    include_counts: bool = False,
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
    counts = None
    if include_counts:
        counts = article_hub_counts(session, article_id=int(article.id))
    return _article_to_public_out(
        article,
        metadata=meta_by_id.get(int(article.id), []),
        include_preview=include_preview,
        include_provenance=True,
        counts=counts,
    )
