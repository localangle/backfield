"""Keyset-paged export of a Stylebook's canonicals for keyed cleanup clients.

The export is a cheap, uniform read: one row per active canonical with counts, so a toolkit can pull
the whole catalog (or an incremental slice) without calling the interactive Stylebook routes.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from backfield_db import SubstrateArticle
from pydantic import BaseModel, Field
from sqlalchemy import exists, func
from sqlmodel import Session, col, select

from backfield_entities.cleanup.cursor import decode_cursor, encode_cursor
from backfield_entities.cleanup.entity_models import CleanupEntityModels, EntityName

EXPORT_DEFAULT_LIMIT = 500
EXPORT_MAX_LIMIT = 1000
_ID_CHUNK_SIZE = 500


class ExportCursor(BaseModel):
    """Keyset position: the last canonical id already returned (ids are sorted ascending)."""

    after_id: str


class ExportPoint(BaseModel):
    lat: float
    lon: float


class LocationExportDetails(BaseModel):
    formatted_address: str | None = None
    geometry_type: str | None = None
    point: ExportPoint | None = None
    country_code: str | None = None
    subdivision_code: str | None = None
    city_name: str | None = None
    district_kind: str | None = None
    district_number: str | None = None


class PersonExportDetails(BaseModel):
    title: str | None = None
    affiliation: str | None = None
    public_figure: bool = False


class OrganizationExportDetails(BaseModel):
    """Organizations carry no kind-specific fields beyond ``kind`` today."""


ExportDetails = LocationExportDetails | PersonExportDetails | OrganizationExportDetails


class CleanupExportItem(BaseModel):
    id: str
    label: str
    slug: str
    kind: str | None = Field(
        default=None,
        description="Place kind, person type or organization type.",
    )
    mention_count: int = Field(
        description="Active mentions. Counts only mentions inside the date range when one is set."
    )
    story_count: int = Field(description="Distinct articles behind those mentions.")
    alias_count: int = Field(description="Aliases that are not suppressed.")
    created_at: datetime
    updated_at: datetime
    details: ExportDetails


class CleanupExportPage(BaseModel):
    entity: EntityName
    items: list[CleanupExportItem]
    next_cursor: str | None = Field(
        default=None,
        description="Pass as `cursor` to fetch the next page; null on the last page.",
    )


class ExportFilters(BaseModel):
    """Optional narrowing of the export."""

    updated_since: datetime | None = None
    mentioned_from: date | None = None
    mentioned_to: date | None = None
    kind: str | None = None


def _mention_article_conditions(
    models: CleanupEntityModels, filters: ExportFilters
) -> list[object]:
    """WHERE fragments restricting mentions to active ones inside the date range."""
    conditions: list[object] = [models.mention.deleted == False]  # noqa: E712
    if filters.mentioned_from is not None:
        conditions.append(SubstrateArticle.pub_date >= filters.mentioned_from)
    if filters.mentioned_to is not None:
        conditions.append(SubstrateArticle.pub_date <= filters.mentioned_to)
    return conditions


def _has_mention_in_range(models: CleanupEntityModels, filters: ExportFilters) -> object:
    """EXISTS: the canonical has an active mention inside the date range."""
    substrate_canonical = models.column(models.substrate, models.substrate_canonical_column)
    mention_substrate = models.column(models.mention, models.mention_substrate_column)
    return exists(
        select(1)
        .select_from(models.substrate)
        .join(models.mention, mention_substrate == models.substrate.id)
        .join(SubstrateArticle, SubstrateArticle.id == models.mention.article_id)
        .where(
            substrate_canonical == models.canonical.id,
            *_mention_article_conditions(models, filters),
        )
    )


def canonical_mention_counts(
    session: Session,
    models: CleanupEntityModels,
    filters: ExportFilters,
    canonical_ids: list[str],
) -> dict[str, tuple[int, int]]:
    """Return ``{canonical_id: (mention_count, story_count)}`` for a page of canonicals."""
    if not canonical_ids:
        return {}
    substrate_canonical = models.column(models.substrate, models.substrate_canonical_column)
    mention_substrate = models.column(models.mention, models.mention_substrate_column)
    rows = session.exec(
        select(
            substrate_canonical,
            func.count(func.distinct(models.mention.id)),
            func.count(func.distinct(models.mention.article_id)),
        )
        .select_from(models.substrate)
        .join(models.mention, mention_substrate == models.substrate.id)
        .join(SubstrateArticle, SubstrateArticle.id == models.mention.article_id)
        .where(
            col(substrate_canonical).in_(canonical_ids),
            *_mention_article_conditions(models, filters),
        )
        .group_by(substrate_canonical)
    ).all()
    return {str(row[0]): (int(row[1]), int(row[2])) for row in rows}


def canonical_ids_mentioned_in_range(
    session: Session,
    models: CleanupEntityModels,
    canonical_ids: set[str],
    filters: ExportFilters,
) -> set[str]:
    """Return the ids that have an active mention inside the filters' date range."""
    if not canonical_ids:
        return set()
    substrate_canonical = models.column(models.substrate, models.substrate_canonical_column)
    mention_substrate = models.column(models.mention, models.mention_substrate_column)
    found: set[str] = set()
    ordered = sorted(canonical_ids)
    for start in range(0, len(ordered), _ID_CHUNK_SIZE):
        chunk = ordered[start : start + _ID_CHUNK_SIZE]
        rows = session.exec(
            select(substrate_canonical)
            .select_from(models.substrate)
            .join(models.mention, mention_substrate == models.substrate.id)
            .join(SubstrateArticle, SubstrateArticle.id == models.mention.article_id)
            .where(
                col(substrate_canonical).in_(chunk),
                *_mention_article_conditions(models, filters),
            )
            .distinct()
        ).all()
        found.update(str(row) for row in rows)
    return found


def canonical_alias_counts(
    session: Session, models: CleanupEntityModels, canonical_ids: list[str]
) -> dict[str, int]:
    if not canonical_ids:
        return {}
    alias_canonical = models.column(models.alias, models.alias_canonical_column)
    rows = session.exec(
        select(alias_canonical, func.count(models.alias.id))
        .where(
            col(alias_canonical).in_(canonical_ids),
            models.alias.suppressed == False,  # noqa: E712
        )
        .group_by(alias_canonical)
    ).all()
    return {str(row[0]): int(row[1]) for row in rows}


def point_from_geometry_json(geometry_json: dict | None) -> ExportPoint | None:
    if not isinstance(geometry_json, dict) or geometry_json.get("type") != "Point":
        return None
    coordinates = geometry_json.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None
    try:
        return ExportPoint(lon=float(coordinates[0]), lat=float(coordinates[1]))
    except (TypeError, ValueError):
        return None


def canonical_export_details(models: CleanupEntityModels, canonical: Any) -> ExportDetails:
    if models.name == "locations":
        return LocationExportDetails(
            formatted_address=canonical.formatted_address,
            geometry_type=canonical.geometry_type,
            point=point_from_geometry_json(canonical.geometry_json),
            country_code=canonical.country_code,
            subdivision_code=canonical.subdivision_code,
            city_name=canonical.city_name,
            district_kind=canonical.district_kind,
            district_number=canonical.district_number,
        )
    if models.name == "people":
        return PersonExportDetails(
            title=canonical.title,
            affiliation=canonical.affiliation,
            public_figure=bool(canonical.public_figure),
        )
    return OrganizationExportDetails()


def _canonical_query(
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    filters: ExportFilters,
    after_id: str | None,
    limit: int,
) -> object:
    canonical = models.canonical
    statement = select(canonical).where(
        canonical.stylebook_id == stylebook_id,
        canonical.status == "active",
    )
    if after_id is not None:
        statement = statement.where(canonical.id > after_id)
    if filters.updated_since is not None:
        statement = statement.where(canonical.updated_at >= filters.updated_since)
    if filters.kind:
        statement = statement.where(
            func.lower(models.column(canonical, models.kind_column)) == filters.kind.strip().lower()
        )
    if filters.mentioned_from is not None or filters.mentioned_to is not None:
        statement = statement.where(_has_mention_in_range(models, filters))
    return statement.order_by(canonical.id).limit(limit + 1)


def export_canonicals(
    session: Session,
    models: CleanupEntityModels,
    *,
    stylebook_id: int,
    filters: ExportFilters,
    cursor: str | None = None,
    limit: int = EXPORT_DEFAULT_LIMIT,
) -> CleanupExportPage:
    """Return one page of active canonicals ordered by id.

    Raises ``InvalidCursorError`` when ``cursor`` cannot be decoded.
    """
    after_id = decode_cursor(cursor, ExportCursor).after_id if cursor else None
    rows = list(
        session.exec(
            _canonical_query(
                models, stylebook_id=stylebook_id, filters=filters, after_id=after_id, limit=limit
            )
        ).all()
    )
    has_more = len(rows) > limit
    page_rows = rows[:limit]
    page_ids = [str(row.id) for row in page_rows]
    counts = canonical_mention_counts(session, models, filters, page_ids)
    alias_counts = canonical_alias_counts(session, models, page_ids)
    items = [
        CleanupExportItem(
            id=str(row.id),
            label=str(row.label),
            slug=str(row.slug),
            kind=models.canonical_kind(row),
            mention_count=counts.get(str(row.id), (0, 0))[0],
            story_count=counts.get(str(row.id), (0, 0))[1],
            alias_count=alias_counts.get(str(row.id), 0),
            created_at=row.created_at,
            updated_at=row.updated_at,
            details=canonical_export_details(models, row),
        )
        for row in page_rows
    ]
    next_cursor = (
        encode_cursor(ExportCursor(after_id=page_ids[-1])) if has_more and page_ids else None
    )
    return CleanupExportPage(entity=models.name, items=items, next_cursor=next_cursor)
