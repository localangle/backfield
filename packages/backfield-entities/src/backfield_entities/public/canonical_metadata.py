"""Load and attach typed Stylebook canonical metadata for public entity responses."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from sqlmodel import Session, col, select

from backfield_entities.catalog.canonical_meta import (
    AttrClause,
    MetaValueType,
    apply_attr_clauses_to_filters,
    meta_row_to_api,
)


class PublicCanonicalMetaOut(BaseModel):
    meta_type: str
    value_type: MetaValueType
    value: str | float | bool


def load_meta_by_canonical_ids(
    session: Session,
    *,
    meta_model: type[Any],
    canonical_fk_attr: str,
    canonical_ids: list[str],
) -> dict[str, list[PublicCanonicalMetaOut]]:
    """Batch-load metadata rows keyed by canonical id string."""
    if not canonical_ids:
        return {}
    fk = getattr(meta_model, canonical_fk_attr)
    rows = session.exec(
        select(meta_model)
        .where(col(fk).in_(canonical_ids))
        .order_by(col(meta_model.meta_type), col(meta_model.id))
    ).all()
    out: dict[str, list[PublicCanonicalMetaOut]] = {cid: [] for cid in canonical_ids}
    for row in rows:
        cid = str(getattr(row, canonical_fk_attr))
        payload = meta_row_to_api(row, include_id=False)
        out.setdefault(cid, []).append(PublicCanonicalMetaOut(**payload))
    return out


def append_attr_filters(
    filters: list[Any],
    *,
    meta_model: type[Any],
    canonical_fk_attr: str,
    canonical_id_column: Any,
    attr_clauses: tuple[AttrClause, ...],
) -> None:
    apply_attr_clauses_to_filters(
        filters,
        meta_model=meta_model,
        canonical_fk_attr=canonical_fk_attr,
        canonical_id_column=canonical_id_column,
        clauses=attr_clauses,
    )


__all__ = [
    "PublicCanonicalMetaOut",
    "append_attr_filters",
    "load_meta_by_canonical_ids",
]
