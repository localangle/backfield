"""Find location canonicals with no stored geometry."""

from __future__ import annotations

from backfield_db import StylebookLocationCanonical
from sqlalchemy import String, and_, cast, literal, or_
from sqlmodel import Session, col, func, select

from backfield_entities.quality.types import CleanupLocationCanonicalRow


def _missing_geometry_json_filter():
    geometry_json_col = col(StylebookLocationCanonical.geometry_json)
    return or_(
        geometry_json_col.is_(None),
        cast(geometry_json_col, String) == literal("null"),
    )


def _missing_geometry_where(session: Session, stylebook_id: int):
    filters: list = [
        StylebookLocationCanonical.stylebook_id == stylebook_id,
        _missing_geometry_json_filter(),
    ]
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        filters.append(col(StylebookLocationCanonical.geometry).is_(None))
    return and_(*filters)


def count_missing_geometry_locations(session: Session, *, stylebook_id: int) -> int:
    return int(
        session.scalar(
            select(func.count())
            .select_from(StylebookLocationCanonical)
            .where(_missing_geometry_where(session, stylebook_id))
        )
        or 0
    )


def list_missing_geometry_locations(
    session: Session,
    *,
    stylebook_id: int,
    limit: int,
    offset: int,
) -> tuple[list[CleanupLocationCanonicalRow], int]:
    where = _missing_geometry_where(session, stylebook_id)
    total = int(
        session.scalar(select(func.count()).select_from(StylebookLocationCanonical).where(where))
        or 0
    )
    rows = session.exec(
        select(StylebookLocationCanonical)
        .where(where)
        .order_by(func.lower(StylebookLocationCanonical.label).asc())
        .offset(offset)
        .limit(limit)
    ).all()
    items = [
        CleanupLocationCanonicalRow(
            id=str(row.id),
            slug=str(row.slug),
            label=str(row.label),
            location_type=str(row.location_type) if row.location_type else None,
            status=str(row.status),
        )
        for row in rows
        if row.id is not None
    ]
    return items, total
