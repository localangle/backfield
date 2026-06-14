"""Semantic article search over ``substrate_article_embedding`` rows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from backfield_db import SubstrateArticle, SubstrateArticleEmbedding
from sqlalchemy import and_, or_
from sqlmodel import Session, col, select

from backfield_entities.ingest.semantic_indexing.search import (
    _coerce_embedding_vector,
    cosine_similarity,
)
from backfield_entities.public.articles import (
    PublicArticleOut,
    _apply_public_article_list_filters,
    _article_to_public_out,
    _meta_rows_for_articles,
)


class PublicArticleSemanticSearchItemOut(PublicArticleOut):
    score: float


@dataclass(frozen=True)
class PublicArticleSemanticSearchParams:
    meta_type: str | None = None
    meta_category: str | None = None
    pub_date_from: date | None = None
    pub_date_to: date | None = None
    limit: int = 25
    offset: int = 0
    include_preview: bool = False


def _embedding_rows_for_project(
    session: Session,
    *,
    project_id: int,
    embedding_model_config_id: str,
    embedding_provider_model_id: str,
    params: PublicArticleSemanticSearchParams,
) -> list[tuple[SubstrateArticle, SubstrateArticleEmbedding]]:
    stmt = (
        select(SubstrateArticle, SubstrateArticleEmbedding)
        .join(
            SubstrateArticleEmbedding,
            col(SubstrateArticleEmbedding.article_id) == col(SubstrateArticle.id),
        )
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            col(SubstrateArticleEmbedding.embedding).isnot(None),
            or_(
                SubstrateArticleEmbedding.embedding_ai_model_config_id
                == embedding_model_config_id,
                and_(
                    col(SubstrateArticleEmbedding.embedding_ai_model_config_id).is_(None),
                    SubstrateArticleEmbedding.embedding_model == embedding_provider_model_id,
                ),
            ),
        )
    )
    stmt = _apply_public_article_list_filters(
        stmt,
        meta_type=params.meta_type,
        meta_category=params.meta_category,
        pub_date_from=params.pub_date_from,
        pub_date_to=params.pub_date_to,
    )
    return list(session.exec(stmt).all())


def _coerce_sqlite_embedding(raw: object | None) -> list[float] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return _coerce_embedding_vector(parsed)
    return _coerce_embedding_vector(raw)


def search_public_articles_semantic(
    session: Session,
    *,
    project_id: int,
    query_vector: list[float],
    embedding_model_config_id: str,
    embedding_provider_model_id: str,
    params: PublicArticleSemanticSearchParams,
) -> tuple[list[PublicArticleSemanticSearchItemOut], int]:
    """Rank project articles by cosine similarity when an embedding row exists."""
    rows = _embedding_rows_for_project(
        session,
        project_id=project_id,
        embedding_model_config_id=embedding_model_config_id,
        embedding_provider_model_id=embedding_provider_model_id,
        params=params,
    )

    ranked: list[tuple[float, SubstrateArticle]] = []
    for article, embedding_row in rows:
        vector = _coerce_embedding_vector(getattr(embedding_row, "embedding", None))
        if vector is None:
            vector = _coerce_sqlite_embedding(getattr(embedding_row, "embedding", None))
        if vector is None or len(vector) != len(query_vector):
            continue
        score = cosine_similarity(query_vector, vector)
        ranked.append((score, article))

    ranked.sort(
        key=lambda item: (
            -item[0],
            item[1].pub_date.isoformat() if item[1].pub_date is not None else "",
            -int(item[1].id or 0),
        )
    )
    total = len(ranked)
    page = ranked[params.offset : params.offset + params.limit]

    article_ids = [int(article.id) for _, article in page if article.id is not None]
    meta_by_id = _meta_rows_for_articles(session, article_ids)

    items = [
        PublicArticleSemanticSearchItemOut(
            **_article_to_public_out(
                article,
                metadata=meta_by_id.get(int(article.id), []),  # type: ignore[arg-type]
                include_preview=params.include_preview,
                include_provenance=False,
            ).model_dump(),
            score=score,
        )
        for score, article in page
    ]
    return items, total
