"""Shared helpers for public mention routes."""

from __future__ import annotations

from datetime import date

from backfield_db import BackfieldProject
from backfield_entities.public.article_hub import PublicEntityMentionType
from backfield_entities.public.articles import ArticleMetaClause
from backfield_entities.public.mentions import PublicMentionSearchParams


def resolve_public_mentions_scope(project: BackfieldProject) -> int:
    return int(project.id)  # type: ignore[arg-type]


def build_mention_search_params(
    *,
    entity_type: PublicEntityMentionType | None,
    q: str | None,
    nature: str | None,
    has_canonical: bool | None,
    author: str | None,
    external_source: str | None,
    section: str | None,
    meta_type: str | None,
    meta_category: str | None,
    exclude_meta_type: str | None,
    exclude_meta_category: str | None,
    meta_clauses: tuple[ArticleMetaClause, ...] = (),
    location_type: str | None,
    person_type: str | None,
    organization_type: str | None,
    public_figure: bool | None,
    pub_date_from: date | None,
    pub_date_to: date | None,
    limit: int,
    offset: int,
) -> PublicMentionSearchParams:
    return PublicMentionSearchParams(
        entity_type=entity_type,
        q=q,
        nature=nature,
        has_canonical=has_canonical,
        author=author,
        external_source=external_source,
        section=section,
        meta_type=meta_type,
        meta_category=meta_category,
        exclude_meta_type=exclude_meta_type,
        exclude_meta_category=exclude_meta_category,
        meta_clauses=meta_clauses,
        location_type=location_type,
        person_type=person_type,
        organization_type=organization_type,
        public_figure=public_figure,
        pub_date_from=pub_date_from,
        pub_date_to=pub_date_to,
        limit=limit,
        offset=offset,
    )
