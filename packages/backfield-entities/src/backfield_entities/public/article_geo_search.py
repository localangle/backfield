"""Geographic article search via location mention geometry."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Literal

from backfield_db import SubstrateArticle, SubstrateLocation, SubstrateLocationMention
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlmodel import Session, col, select

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

MILES_TO_METERS = 1609.34
EARTH_RADIUS_MILES = 3958.7613


class PublicArticleGeoSearchMode(StrEnum):
    point = "point"
    bbox = "bbox"


@dataclass(frozen=True)
class PublicArticleGeoSearchParams:
    mode: PublicArticleGeoSearchMode
    center_lng: float | None = None
    center_lat: float | None = None
    radius_miles: float | None = None
    min_lng: float | None = None
    min_lat: float | None = None
    max_lng: float | None = None
    max_lat: float | None = None
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
    include_preview: bool = False


class PublicArticleGeoSearchItemOut(BaseModel):
    article: PublicArticleOut
    matching_locations: list[PublicArticleLocationOut] = Field(default_factory=list)
    search_mode: Literal["point", "bbox"]


def _point_coordinates(geometry_json: dict | None) -> tuple[float, float] | None:
    if not isinstance(geometry_json, dict):
        return None
    geom_type = geometry_json.get("type")
    coordinates = geometry_json.get("coordinates")
    if geom_type == "Point" and isinstance(coordinates, list) and len(coordinates) >= 2:
        return float(coordinates[0]), float(coordinates[1])
    return None


def _haversine_miles(lng1: float, lat1: float, lng2: float, lat2: float) -> float:
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(min(1.0, math.sqrt(a)))


def _sqlite_geometry_matches(
    geometry_json: dict | None,
    *,
    params: PublicArticleGeoSearchParams,
) -> bool:
    point = _point_coordinates(geometry_json)
    if point is None:
        return False
    lng, lat = point
    if params.mode is PublicArticleGeoSearchMode.point:
        assert params.center_lng is not None
        assert params.center_lat is not None
        assert params.radius_miles is not None
        return (
            _haversine_miles(params.center_lng, params.center_lat, lng, lat) <= params.radius_miles
        )
    assert params.min_lng is not None
    assert params.min_lat is not None
    assert params.max_lng is not None
    assert params.max_lat is not None
    return params.min_lng <= lng <= params.max_lng and params.min_lat <= lat <= params.max_lat


def _postgres_matching_pairs(
    session: Session,
    *,
    project_id: int,
    params: PublicArticleGeoSearchParams,
) -> list[tuple[int, int]]:
    bind: dict[str, object] = {"project_id": project_id}
    location_type_filter = ""
    if (params.location_type or "").strip():
        bind["location_type"] = params.location_type.strip()
        location_type_filter = "AND sl.location_type = :location_type"
    nature_filter = ""
    if (params.nature or "").strip():
        bind["nature"] = params.nature.strip()
        nature_filter = "AND lm.nature = :nature"

    if params.mode is PublicArticleGeoSearchMode.point:
        assert params.center_lng is not None
        assert params.center_lat is not None
        assert params.radius_miles is not None
        bind["center_lng"] = params.center_lng
        bind["center_lat"] = params.center_lat
        bind["radius_meters"] = params.radius_miles * MILES_TO_METERS
        area_cte = """
        WITH search_area AS (
            SELECT ST_Buffer(
                ST_SetSRID(ST_MakePoint(:center_lng, :center_lat), 4326)::geography,
                :radius_meters
            ) AS geom
        )
        """
    else:
        assert params.min_lng is not None
        assert params.min_lat is not None
        assert params.max_lng is not None
        assert params.max_lat is not None
        bind.update(
            {
                "min_lng": params.min_lng,
                "min_lat": params.min_lat,
                "max_lng": params.max_lng,
                "max_lat": params.max_lat,
            }
        )
        area_cte = """
        WITH search_area AS (
            SELECT ST_SetSRID(
                ST_MakeEnvelope(:min_lng, :min_lat, :max_lng, :max_lat, 4326),
                4326
            )::geography AS geom
        )
        """

    stmt = text(
        area_cte
        + """
        SELECT lm.id AS mention_id, lm.article_id
        FROM substrate_location_mention lm
        INNER JOIN substrate_article a ON a.id = lm.article_id
        INNER JOIN substrate_location sl ON sl.id = lm.location_id
        CROSS JOIN search_area sa
        WHERE a.project_id = :project_id
          AND a.deleted = false
          AND lm.deleted = false
          AND sl.geometry IS NOT NULL
          AND ST_DWithin(sl.geometry::geography, sa.geom, 0)
        """
        + location_type_filter
        + nature_filter
    )
    rows = session.exec(stmt.bindparams(**bind)).all()
    if not rows:
        return []

    article_ids = {int(row.article_id) for row in rows}
    article_filter_stmt = select(SubstrateArticle.id).where(
        col(SubstrateArticle.id).in_(article_ids),
        SubstrateArticle.project_id == project_id,
        SubstrateArticle.deleted == False,  # noqa: E712
    )
    article_filter_stmt = _apply_public_article_list_filters(
        article_filter_stmt,
        meta_type=params.meta_type,
        meta_category=params.meta_category,
        exclude_meta_type=params.exclude_meta_type,
        exclude_meta_category=params.exclude_meta_category,
        meta_clauses=params.meta_clauses,
        pub_date_from=params.pub_date_from,
        pub_date_to=params.pub_date_to,
    )
    allowed_article_ids = {int(aid) for aid in session.exec(article_filter_stmt).all()}
    return [
        (int(row.mention_id), int(row.article_id))
        for row in rows
        if int(row.article_id) in allowed_article_ids
    ]


def _sqlite_matching_pairs(
    session: Session,
    *,
    project_id: int,
    params: PublicArticleGeoSearchParams,
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
    stmt = _apply_public_article_list_filters(
        stmt,
        meta_type=params.meta_type,
        meta_category=params.meta_category,
        exclude_meta_type=params.exclude_meta_type,
        exclude_meta_category=params.exclude_meta_category,
        meta_clauses=params.meta_clauses,
        pub_date_from=params.pub_date_from,
        pub_date_to=params.pub_date_to,
    )
    location_type = (params.location_type or "").strip()
    if location_type:
        stmt = stmt.where(SubstrateLocation.location_type == location_type)
    nature = (params.nature or "").strip()
    if nature:
        stmt = stmt.where(SubstrateLocationMention.nature == nature)

    pairs: list[tuple[int, int]] = []
    for mention, loc, _article in session.exec(stmt).all():
        if mention.id is None:
            continue
        if not _sqlite_geometry_matches(loc.geometry_json, params=params):
            continue
        pairs.append((int(mention.id), int(mention.article_id)))
    return pairs


def group_and_page_articles_by_mention_pairs(
    session: Session,
    *,
    pairs: list[tuple[int, int]],
    limit: int,
    offset: int,
) -> tuple[list[tuple[int, list[int]]], int]:
    mentions_by_article: dict[int, list[int]] = {}
    for mention_id, article_id in pairs:
        mentions_by_article.setdefault(article_id, []).append(mention_id)

    if not mentions_by_article:
        return [], 0

    article_ids = list(mentions_by_article.keys())
    articles = session.exec(
        select(SubstrateArticle)
        .where(col(SubstrateArticle.id).in_(article_ids))
        .order_by(
            col(SubstrateArticle.pub_date).desc().nulls_last(),
            col(SubstrateArticle.id).desc(),
        )
    ).all()
    ordered_article_ids = [int(a.id) for a in articles if a.id is not None]
    total = len(ordered_article_ids)
    page_article_ids = ordered_article_ids[offset : offset + limit]
    page = [
        (article_id, mentions_by_article.get(article_id, [])) for article_id in page_article_ids
    ]
    return page, total


def group_and_page_articles_by_mention_cell_triples(
    session: Session,
    *,
    triples: list[tuple[int, int, str]],
    limit: int,
    offset: int,
) -> tuple[list[tuple[int, list[int], list[str]]], int]:
    """Group mention matches by article, merge matched H3 cells, and page globally."""
    mentions_by_article: dict[int, list[int]] = {}
    cells_by_article: dict[int, set[str]] = {}
    for mention_id, article_id, display_cell in triples:
        mentions_by_article.setdefault(article_id, []).append(mention_id)
        cells_by_article.setdefault(article_id, set()).add(display_cell)

    if not mentions_by_article:
        return [], 0

    article_ids = list(mentions_by_article.keys())
    articles = session.exec(
        select(SubstrateArticle)
        .where(col(SubstrateArticle.id).in_(article_ids))
        .order_by(
            col(SubstrateArticle.pub_date).desc().nulls_last(),
            col(SubstrateArticle.id).desc(),
        )
    ).all()
    ordered_article_ids = [int(a.id) for a in articles if a.id is not None]
    total = len(ordered_article_ids)
    page_article_ids = ordered_article_ids[offset : offset + limit]
    page = [
        (
            article_id,
            mentions_by_article.get(article_id, []),
            sorted(cells_by_article.get(article_id, set())),
        )
        for article_id in page_article_ids
    ]
    return page, total


def search_public_articles_by_geo(
    session: Session,
    *,
    project_id: int,
    params: PublicArticleGeoSearchParams,
) -> tuple[list[PublicArticleGeoSearchItemOut], int]:
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        pairs = _postgres_matching_pairs(session, project_id=project_id, params=params)
    else:
        pairs = _sqlite_matching_pairs(session, project_id=project_id, params=params)

    page, total = group_and_page_articles_by_mention_pairs(
        session,
        pairs=pairs,
        limit=params.limit,
        offset=params.offset,
    )
    if not page:
        return [], total

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

    mode: Literal["point", "bbox"] = params.mode.value
    items: list[PublicArticleGeoSearchItemOut] = []
    for article_id, mention_ids in page:
        article = articles.get(article_id)
        if article is None:
            continue
        matching_locations = [
            locations_by_mention_id[mid] for mid in mention_ids if mid in locations_by_mention_id
        ]
        items.append(
            PublicArticleGeoSearchItemOut(
                article=_article_to_public_out(
                    article,
                    metadata=meta_by_id.get(article_id, []),
                    include_preview=params.include_preview,
                ),
                matching_locations=matching_locations,
                search_mode=mode,
            )
        )
    return items, total
