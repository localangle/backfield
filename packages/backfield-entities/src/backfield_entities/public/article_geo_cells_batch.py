"""Batch article drill-down for multiple H3 geo-cells hexes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from backfield_db import SubstrateArticle, SubstrateLocation, SubstrateLocationMention
from pydantic import BaseModel, Field
from sqlalchemy import bindparam, text
from sqlmodel import Session, col, select

from backfield_entities.public.article_geo_cell_detail import (
    PublicArticleGeoMentionFilters,
    display_cell_for_location,
    filter_allowed_article_ids,
)
from backfield_entities.public.article_geo_search import (
    group_and_page_articles_by_mention_cell_triples,
)
from backfield_entities.public.article_hub import (
    PublicArticleLocationOut,
    location_mentions_out_by_ids,
)
from backfield_entities.public.articles import (
    PublicArticleOut,
    _article_to_public_out,
    _meta_rows_for_articles,
)

MAX_CELLS_PER_BATCH_QUERY = 200


class PublicArticleGeoCellsBatchValidationError(ValueError):
    """Invalid batch geo-cell query parameters."""


@dataclass(frozen=True)
class PublicArticleGeoCellsBatchParams:
    cells: tuple[str, ...]
    resolution: int
    location_type: str | None = None
    nature: str | None = None
    meta_type: str | None = None
    meta_category: str | None = None
    exclude_meta_type: str | None = None
    exclude_meta_category: str | None = None
    external_source: str | None = None
    pub_date_from: date | None = None
    pub_date_to: date | None = None
    limit: int = 25
    offset: int = 0
    include_preview: bool = False


class PublicArticleGeoCellTotalOut(BaseModel):
    h3_cell: str
    article_count: int


class PublicArticleGeoCellsBatchItemOut(BaseModel):
    article: PublicArticleOut
    matching_locations: list[PublicArticleLocationOut] = Field(default_factory=list)
    matched_cells: list[str] = Field(default_factory=list)


class PublicArticleGeoCellsBatchResult(BaseModel):
    resolution: int
    items: list[PublicArticleGeoCellsBatchItemOut] = Field(default_factory=list)
    per_cell_totals: list[PublicArticleGeoCellTotalOut] = Field(default_factory=list)
    total: int = 0


def normalize_batch_cells(cells: list[str], *, resolution: int) -> tuple[str, ...]:
    from h3 import get_resolution, is_valid_cell

    if not cells:
        raise PublicArticleGeoCellsBatchValidationError("cells must not be empty.")
    if len(cells) > MAX_CELLS_PER_BATCH_QUERY:
        raise PublicArticleGeoCellsBatchValidationError(
            f"cells must not exceed {MAX_CELLS_PER_BATCH_QUERY} entries."
        )

    normalized: list[str] = []
    seen: set[str] = set()
    for raw in cells:
        cell = raw.strip()
        if not cell:
            raise PublicArticleGeoCellsBatchValidationError("cells must not contain empty values.")
        if not is_valid_cell(cell):
            raise PublicArticleGeoCellsBatchValidationError(f"Invalid h3_cell: {cell}.")
        cell_resolution = int(get_resolution(cell))
        if cell_resolution != resolution:
            raise PublicArticleGeoCellsBatchValidationError(
                f"h3_cell {cell} resolution {cell_resolution} does not match requested "
                f"resolution {resolution}."
            )
        if cell not in seen:
            seen.add(cell)
            normalized.append(cell)
    return tuple(normalized)


def _mention_filters(params: PublicArticleGeoCellsBatchParams) -> PublicArticleGeoMentionFilters:
    return PublicArticleGeoMentionFilters(
        location_type=params.location_type,
        nature=params.nature,
        meta_type=params.meta_type,
        meta_category=params.meta_category,
        exclude_meta_type=params.exclude_meta_type,
        exclude_meta_category=params.exclude_meta_category,
        external_source=params.external_source,
        pub_date_from=params.pub_date_from,
        pub_date_to=params.pub_date_to,
    )


def _location_filters_sql(
    filters: PublicArticleGeoMentionFilters,
    bind: dict[str, object],
) -> tuple[str, str]:
    location_type_filter = ""
    if (filters.location_type or "").strip():
        bind["location_type"] = filters.location_type.strip()
        location_type_filter = "AND sl.location_type = :location_type"
    nature_filter = ""
    if (filters.nature or "").strip():
        bind["nature"] = filters.nature.strip()
        nature_filter = "AND lm.nature = :nature"
    return location_type_filter, nature_filter


def _postgres_matching_triples(
    session: Session,
    *,
    project_id: int,
    cells: tuple[str, ...],
    display_resolution: int,
    filters: PublicArticleGeoMentionFilters,
) -> list[tuple[int, int, str]]:
    bind: dict[str, object] = {
        "project_id": project_id,
        "r": display_resolution,
        "cells": list(cells),
    }
    location_type_filter, nature_filter = _location_filters_sql(filters, bind)
    stmt = text(
        """
        SELECT lm.id AS mention_id,
               lm.article_id,
               CASE
                 WHEN sl.h3_resolution = :r THEN sl.h3_cell
                 ELSE h3_cell_to_parent(sl.h3_cell::h3index, :r)::text
               END AS display_cell
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
            CASE
              WHEN sl.h3_resolution = :r THEN sl.h3_cell
              ELSE h3_cell_to_parent(sl.h3_cell::h3index, :r)::text
            END
          ) IN :cells
        """
        + location_type_filter
        + nature_filter
    ).bindparams(bindparam("cells", expanding=True))
    rows = session.exec(stmt, params=bind).all()
    if not rows:
        return []

    article_ids = {int(row.article_id) for row in rows}
    allowed_article_ids = filter_allowed_article_ids(
        session,
        project_id=project_id,
        article_ids=article_ids,
        filters=filters,
    )
    return [
        (int(row.mention_id), int(row.article_id), str(row.display_cell))
        for row in rows
        if int(row.article_id) in allowed_article_ids
    ]


def _sqlite_matching_triples(
    session: Session,
    *,
    project_id: int,
    cells: tuple[str, ...],
    display_resolution: int,
    filters: PublicArticleGeoMentionFilters,
) -> list[tuple[int, int, str]]:
    cells_set = set(cells)
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
    location_type = (filters.location_type or "").strip()
    if location_type:
        stmt = stmt.where(SubstrateLocation.location_type == location_type)
    nature = (filters.nature or "").strip()
    if nature:
        stmt = stmt.where(SubstrateLocationMention.nature == nature)

    candidate_triples: list[tuple[int, int, str]] = []
    candidate_article_ids: set[int] = set()
    for mention, loc, _article in session.exec(stmt).all():
        if mention.id is None or mention.article_id is None:
            continue
        if loc.h3_cell is None or loc.h3_resolution is None:
            continue
        display_cell = display_cell_for_location(
            native_h3_cell=str(loc.h3_cell),
            native_h3_resolution=int(loc.h3_resolution),
            display_resolution=display_resolution,
        )
        if display_cell is None or display_cell not in cells_set:
            continue
        article_id = int(mention.article_id)
        candidate_triples.append((int(mention.id), article_id, display_cell))
        candidate_article_ids.add(article_id)

    allowed_article_ids = filter_allowed_article_ids(
        session,
        project_id=project_id,
        article_ids=candidate_article_ids,
        filters=filters,
    )
    return [
        (mention_id, article_id, display_cell)
        for mention_id, article_id, display_cell in candidate_triples
        if article_id in allowed_article_ids
    ]


def _per_cell_totals(
    *,
    requested_cells: tuple[str, ...],
    triples: list[tuple[int, int, str]],
) -> list[PublicArticleGeoCellTotalOut]:
    articles_by_cell: dict[str, set[int]] = {cell: set() for cell in requested_cells}
    for _mention_id, article_id, display_cell in triples:
        if display_cell in articles_by_cell:
            articles_by_cell[display_cell].add(article_id)
    return [
        PublicArticleGeoCellTotalOut(h3_cell=cell, article_count=len(articles_by_cell[cell]))
        for cell in requested_cells
    ]


def search_public_articles_in_cells(
    session: Session,
    *,
    project_id: int,
    params: PublicArticleGeoCellsBatchParams,
) -> PublicArticleGeoCellsBatchResult:
    cells = normalize_batch_cells(list(params.cells), resolution=params.resolution)
    filters = _mention_filters(params)

    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        triples = _postgres_matching_triples(
            session,
            project_id=project_id,
            cells=cells,
            display_resolution=params.resolution,
            filters=filters,
        )
    else:
        triples = _sqlite_matching_triples(
            session,
            project_id=project_id,
            cells=cells,
            display_resolution=params.resolution,
            filters=filters,
        )

    per_cell_totals = _per_cell_totals(requested_cells=cells, triples=triples)
    page, total = group_and_page_articles_by_mention_cell_triples(
        session,
        triples=triples,
        limit=params.limit,
        offset=params.offset,
    )
    if not page:
        return PublicArticleGeoCellsBatchResult(
            resolution=params.resolution,
            items=[],
            per_cell_totals=per_cell_totals,
            total=total,
        )

    page_article_ids = [article_id for article_id, _, _ in page]
    all_mention_ids = [mid for _, mention_ids, _ in page for mid in mention_ids]
    articles = {
        int(a.id): a
        for a in session.exec(
            select(SubstrateArticle).where(col(SubstrateArticle.id).in_(page_article_ids))
        ).all()
        if a.id is not None
    }
    meta_by_id = _meta_rows_for_articles(session, page_article_ids)
    locations_by_mention_id = location_mentions_out_by_ids(session, all_mention_ids)

    items: list[PublicArticleGeoCellsBatchItemOut] = []
    for article_id, mention_ids, matched_cells in page:
        article = articles.get(article_id)
        if article is None:
            continue
        matching_locations = [
            locations_by_mention_id[mid] for mid in mention_ids if mid in locations_by_mention_id
        ]
        items.append(
            PublicArticleGeoCellsBatchItemOut(
                article=_article_to_public_out(
                    article,
                    metadata=meta_by_id.get(article_id, []),
                    include_preview=params.include_preview,
                    include_provenance=False,
                ),
                matching_locations=matching_locations,
                matched_cells=matched_cells,
            )
        )

    return PublicArticleGeoCellsBatchResult(
        resolution=params.resolution,
        items=items,
        per_cell_totals=per_cell_totals,
        total=total,
    )
