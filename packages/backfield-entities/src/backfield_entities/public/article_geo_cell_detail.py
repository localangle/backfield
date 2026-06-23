"""Article drill-down for a single H3 geo-cells hex."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backfield_db import SubstrateArticle, SubstrateLocation, SubstrateLocationMention
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel import Session, col, select

from backfield_entities.public.article_geo_search import group_and_page_articles_by_mention_pairs
from backfield_entities.public.article_hub import (
    PublicArticleLocationOut,
    location_mentions_out_by_ids,
)
from backfield_entities.public.articles import (
    ArticleMetaClause,
    PublicArticleOut,
    _apply_public_article_list_filters,
    _article_to_public_out,
    _meta_rows_for_articles,
)


@dataclass(frozen=True)
class PublicArticleGeoMentionFilters:
    location_type: str | None = None
    nature: str | None = None
    meta_type: str | None = None
    meta_category: str | None = None
    exclude_meta_type: str | None = None
    exclude_meta_category: str | None = None
    meta_clauses: tuple[ArticleMetaClause, ...] = ()
    external_source: str | None = None
    pub_date_from: date | None = None
    pub_date_to: date | None = None


@dataclass(frozen=True)
class PublicArticleGeoCellDetailParams:
    h3_cell: str
    location_type: str | None = None
    nature: str | None = None
    meta_type: str | None = None
    meta_category: str | None = None
    exclude_meta_type: str | None = None
    exclude_meta_category: str | None = None
    meta_clauses: tuple[ArticleMetaClause, ...] = ()
    pub_date_from: date | None = None
    pub_date_to: date | None = None
    limit: int = 25
    offset: int = 0


class PublicArticleGeoCellDetailItemOut(BaseModel):
    article: PublicArticleOut
    matching_locations: list[PublicArticleLocationOut] = Field(default_factory=list)


class PublicArticleGeoCellDetailResult(BaseModel):
    h3_cell: str
    resolution: int
    items: list[PublicArticleGeoCellDetailItemOut] = Field(default_factory=list)
    total: int = 0


def cell_resolution(h3_cell: str) -> int:
    from h3 import get_resolution

    return int(get_resolution(h3_cell))


def display_cell_for_location(
    *,
    native_h3_cell: str,
    native_h3_resolution: int,
    display_resolution: int,
) -> str | None:
    if native_h3_resolution < display_resolution:
        return None
    if native_h3_resolution == display_resolution:
        return native_h3_cell
    from h3 import cell_to_parent

    return str(cell_to_parent(native_h3_cell, display_resolution))


def mention_filters_from_detail_params(
    params: PublicArticleGeoCellDetailParams,
) -> PublicArticleGeoMentionFilters:
    return PublicArticleGeoMentionFilters(
        location_type=params.location_type,
        nature=params.nature,
        meta_type=params.meta_type,
        meta_category=params.meta_category,
        exclude_meta_type=params.exclude_meta_type,
        exclude_meta_category=params.exclude_meta_category,
        meta_clauses=params.meta_clauses,
        pub_date_from=params.pub_date_from,
        pub_date_to=params.pub_date_to,
    )


def _rolls_up_to_cell(
    *,
    native_h3_cell: str,
    native_h3_resolution: int,
    display_cell: str,
    display_resolution: int,
) -> bool:
    rolled_up = display_cell_for_location(
        native_h3_cell=native_h3_cell,
        native_h3_resolution=native_h3_resolution,
        display_resolution=display_resolution,
    )
    return rolled_up == display_cell


def filter_allowed_article_ids(
    session: Session,
    *,
    project_id: int,
    article_ids: set[int],
    filters: PublicArticleGeoMentionFilters,
) -> set[int]:
    if not article_ids:
        return set()
    stmt = select(SubstrateArticle.id).where(
        col(SubstrateArticle.id).in_(article_ids),
        SubstrateArticle.project_id == project_id,
        SubstrateArticle.deleted == False,  # noqa: E712
    )
    stmt = _apply_public_article_list_filters(
        stmt,
        meta_type=filters.meta_type,
        meta_category=filters.meta_category,
        exclude_meta_type=filters.exclude_meta_type,
        exclude_meta_category=filters.exclude_meta_category,
        meta_clauses=filters.meta_clauses,
        external_source=filters.external_source,
        pub_date_from=filters.pub_date_from,
        pub_date_to=filters.pub_date_to,
    )
    return {int(aid) for aid in session.exec(stmt).all()}


def _postgres_matching_pairs(
    session: Session,
    *,
    project_id: int,
    params: PublicArticleGeoCellDetailParams,
    display_resolution: int,
) -> list[tuple[int, int]]:
    bind: dict[str, object] = {
        "project_id": project_id,
        "cell": params.h3_cell,
        "r": display_resolution,
    }
    location_type_filter = ""
    if (params.location_type or "").strip():
        bind["location_type"] = params.location_type.strip()
        location_type_filter = "AND sl.location_type = :location_type"
    nature_filter = ""
    if (params.nature or "").strip():
        bind["nature"] = params.nature.strip()
        nature_filter = "AND lm.nature = :nature"

    stmt = text(
        """
        SELECT lm.id AS mention_id, lm.article_id
        FROM substrate_location_mention lm
        INNER JOIN substrate_article a ON a.id = lm.article_id
        INNER JOIN substrate_location sl ON sl.id = lm.location_id
        WHERE a.project_id = :project_id
          AND a.deleted = false
          AND lm.deleted = false
          AND sl.h3_cell IS NOT NULL
          AND sl.h3_resolution IS NOT NULL
          AND sl.h3_resolution >= :r
          AND (
            (sl.h3_resolution = :r AND sl.h3_cell = :cell)
            OR (
              sl.h3_resolution > :r
              AND h3_cell_to_parent(sl.h3_cell::h3index, :r)::text = :cell
            )
          )
        """
        + location_type_filter
        + nature_filter
    )
    rows = session.exec(stmt.bindparams(**bind)).all()
    if not rows:
        return []

    article_ids = {int(row.article_id) for row in rows}
    allowed_article_ids = filter_allowed_article_ids(
        session,
        project_id=project_id,
        article_ids=article_ids,
        filters=mention_filters_from_detail_params(params),
    )
    return [
        (int(row.mention_id), int(row.article_id))
        for row in rows
        if int(row.article_id) in allowed_article_ids
    ]


def _sqlite_matching_pairs(
    session: Session,
    *,
    project_id: int,
    params: PublicArticleGeoCellDetailParams,
    display_resolution: int,
) -> list[tuple[int, int]]:
    stmt = (
        select(SubstrateLocationMention, SubstrateLocation, SubstrateArticle)
        .join(SubstrateLocation, SubstrateLocation.id == SubstrateLocationMention.location_id)
        .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            SubstrateLocationMention.deleted == False,  # noqa: E712
        )
    )
    location_type = (params.location_type or "").strip()
    if location_type:
        stmt = stmt.where(SubstrateLocation.location_type == location_type)
    nature = (params.nature or "").strip()
    if nature:
        stmt = stmt.where(SubstrateLocationMention.nature == nature)

    candidate_pairs: list[tuple[int, int]] = []
    candidate_article_ids: set[int] = set()
    for mention, loc, _article in session.exec(stmt).all():
        if mention.id is None or mention.article_id is None:
            continue
        if loc.h3_cell is None or loc.h3_resolution is None:
            continue
        if not _rolls_up_to_cell(
            native_h3_cell=str(loc.h3_cell),
            native_h3_resolution=int(loc.h3_resolution),
            display_cell=params.h3_cell,
            display_resolution=display_resolution,
        ):
            continue
        article_id = int(mention.article_id)
        candidate_pairs.append((int(mention.id), article_id))
        candidate_article_ids.add(article_id)

    allowed_article_ids = filter_allowed_article_ids(
        session,
        project_id=project_id,
        article_ids=candidate_article_ids,
        filters=mention_filters_from_detail_params(params),
    )
    return [
        (mention_id, article_id)
        for mention_id, article_id in candidate_pairs
        if article_id in allowed_article_ids
    ]


def search_public_articles_in_cell(
    session: Session,
    *,
    project_id: int,
    params: PublicArticleGeoCellDetailParams,
) -> PublicArticleGeoCellDetailResult:
    display_resolution = cell_resolution(params.h3_cell)

    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        pairs = _postgres_matching_pairs(
            session,
            project_id=project_id,
            params=params,
            display_resolution=display_resolution,
        )
    else:
        pairs = _sqlite_matching_pairs(
            session,
            project_id=project_id,
            params=params,
            display_resolution=display_resolution,
        )

    page, total = group_and_page_articles_by_mention_pairs(
        session,
        pairs=pairs,
        limit=params.limit,
        offset=params.offset,
    )
    if not page:
        return PublicArticleGeoCellDetailResult(
            h3_cell=params.h3_cell,
            resolution=display_resolution,
            items=[],
            total=total,
        )

    page_article_ids = [article_id for article_id, _ in page]
    all_mention_ids = [mid for _, mention_ids in page for mid in mention_ids]
    articles = {
        int(a.id): a
        for a in session.exec(
            select(SubstrateArticle).where(col(SubstrateArticle.id).in_(page_article_ids))
        ).all()
        if a.id is not None
    }
    meta_by_id = _meta_rows_for_articles(session, page_article_ids)
    locations_by_mention_id = location_mentions_out_by_ids(session, all_mention_ids)

    items: list[PublicArticleGeoCellDetailItemOut] = []
    for article_id, mention_ids in page:
        article = articles.get(article_id)
        if article is None:
            continue
        matching_locations = [
            locations_by_mention_id[mid] for mid in mention_ids if mid in locations_by_mention_id
        ]
        items.append(
            PublicArticleGeoCellDetailItemOut(
                article=_article_to_public_out(
                    article,
                    metadata=meta_by_id.get(article_id, []),
                ),
                matching_locations=matching_locations,
            )
        )

    return PublicArticleGeoCellDetailResult(
        h3_cell=params.h3_cell,
        resolution=display_resolution,
        items=items,
        total=total,
    )
