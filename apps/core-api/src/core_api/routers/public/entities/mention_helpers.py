"""Shared helpers for entity-centric mention list routes."""

from __future__ import annotations

from datetime import date
from typing import Literal

from backfield_entities.public.articles import ArticleMetaClause
from backfield_entities.public.mention_filters import PublicEntityMentionListParams


def build_entity_mention_list_params(
    *,
    nature: str | None,
    author: str | None,
    external_source: str | None,
    section: str | None,
    meta_type: str | None,
    meta_category: str | None,
    exclude_meta_type: str | None,
    exclude_meta_category: str | None,
    meta_clauses: tuple[ArticleMetaClause, ...] = (),
    pub_date_from: date | None,
    pub_date_to: date | None,
    quotes_only: bool,
    sort: Literal["article", "created_at"],
    sort_direction: Literal["asc", "desc"],
    limit: int,
    offset: int,
) -> PublicEntityMentionListParams:
    """Build entity mention list params, applying section -> topic metadata sugar."""
    section_value = (section or "").strip()
    resolved_meta_type = meta_type
    resolved_meta_category = meta_category
    if section_value:
        resolved_meta_type = "topic"
        resolved_meta_category = section_value
    return PublicEntityMentionListParams(
        nature=nature,
        author=author,
        external_source=external_source,
        meta_type=resolved_meta_type,
        meta_category=resolved_meta_category,
        exclude_meta_type=exclude_meta_type,
        exclude_meta_category=exclude_meta_category,
        meta_clauses=meta_clauses,
        pub_date_from=pub_date_from,
        pub_date_to=pub_date_to,
        quotes_only=quotes_only,
        sort=sort,
        sort_direction=sort_direction,
        limit=limit,
        offset=offset,
    )
