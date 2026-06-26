"""Shared filter params for entity-centric mention list endpoints."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from backfield_entities.public.articles import ArticleMetaClause, _apply_public_article_list_filters
from backfield_entities.public.mention_evidence import maybe_quotes_only_mention_filters


@dataclass(frozen=True)
class PublicEntityMentionListParams:
    nature: str | None = None
    author: str | None = None
    external_source: str | None = None
    meta_type: str | None = None
    meta_category: str | None = None
    exclude_meta_type: str | None = None
    exclude_meta_category: str | None = None
    meta_clauses: tuple[ArticleMetaClause, ...] = ()
    pub_date_from: date | None = None
    pub_date_to: date | None = None
    quotes_only: bool = False
    sort: Literal["article", "created_at"] = "created_at"
    sort_direction: Literal["asc", "desc"] = "desc"
    limit: int = 25
    offset: int = 0


def apply_entity_mention_list_filters(
    stmt,
    *,
    params: PublicEntityMentionListParams,
    mention_nature_col,
    mention_id_col,
    occurrence_model,
    mention_fk_column: str,
):
    """Apply article, nature, and quote filters to a mention list statement."""
    stmt = _apply_public_article_list_filters(
        stmt,
        meta_type=params.meta_type,
        meta_category=params.meta_category,
        exclude_meta_type=params.exclude_meta_type,
        exclude_meta_category=params.exclude_meta_category,
        meta_clauses=params.meta_clauses,
        author=params.author,
        external_source=params.external_source,
        has_mentions=None,
        pub_date_from=params.pub_date_from,
        pub_date_to=params.pub_date_to,
    )
    nature_value = (params.nature or "").strip()
    if nature_value:
        stmt = stmt.where(mention_nature_col == nature_value)
    if params.quotes_only:
        for clause in maybe_quotes_only_mention_filters(
            mention_id_col,
            occurrence_model=occurrence_model,
            mention_fk_column=mention_fk_column,
            quotes_only=True,
        ):
            stmt = stmt.where(clause)
    return stmt
