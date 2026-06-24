"""Shared helpers for listing articles linked to a canonical entity."""

from __future__ import annotations

from datetime import date

from backfield_db import SubstrateArticle
from sqlmodel import Session, col, select

from backfield_entities.public.article_geo_search import group_and_page_articles_by_mention_pairs
from backfield_entities.public.articles import (
    PublicArticleOut,
    _article_to_public_out,
    _meta_rows_for_articles,
)


def collect_mention_article_pairs(
    session: Session,
    *,
    mention_model: type,
    entity_model: type,
    mention_entity_fk,
    entity_canonical_col,
    canonical_id: str,
    project_id: int,
    nature: str | None = None,
    pub_date_from: date | None = None,
    pub_date_to: date | None = None,
) -> list[tuple[int, int]]:
    filters = [
        entity_canonical_col == canonical_id,
        entity_model.project_id == project_id,
        mention_model.deleted == False,  # noqa: E712
        SubstrateArticle.project_id == project_id,
        SubstrateArticle.deleted == False,  # noqa: E712
    ]
    nature_value = (nature or "").strip()
    if nature_value:
        filters.append(mention_model.nature == nature_value)
    if pub_date_from is not None:
        filters.append(col(SubstrateArticle.pub_date) >= pub_date_from)
    if pub_date_to is not None:
        filters.append(col(SubstrateArticle.pub_date) <= pub_date_to)

    rows = session.exec(
        select(mention_model.id, mention_model.article_id)
        .join(SubstrateArticle, SubstrateArticle.id == mention_model.article_id)
        .join(entity_model, entity_model.id == mention_entity_fk)
        .where(*filters)
    ).all()
    return [
        (int(mention_id), int(article_id))
        for mention_id, article_id in rows
        if mention_id is not None
    ]


def paginate_public_articles_from_mention_pairs(
    session: Session,
    *,
    pairs: list[tuple[int, int]],
    limit: int,
    offset: int,
) -> tuple[list[PublicArticleOut], int]:
    page, total = group_and_page_articles_by_mention_pairs(
        session,
        pairs=pairs,
        limit=limit,
        offset=offset,
    )
    if not page:
        return [], total

    article_ids = [article_id for article_id, _ in page]
    articles = {
        int(article.id): article
        for article in session.exec(
            select(SubstrateArticle).where(col(SubstrateArticle.id).in_(article_ids))
        ).all()
        if article.id is not None
    }
    meta_by_id = _meta_rows_for_articles(session, article_ids)

    items: list[PublicArticleOut] = []
    for article_id, _mention_ids in page:
        article = articles.get(article_id)
        if article is None:
            continue
        items.append(
            _article_to_public_out(
                article,
                metadata=meta_by_id.get(article_id, []),
            )
        )
    return items, total
