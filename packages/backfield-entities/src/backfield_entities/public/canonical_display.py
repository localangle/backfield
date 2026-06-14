"""Display labels for canonical entities in public API responses."""

from __future__ import annotations

from uuid import UUID

from backfield_db import (
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
)
from sqlmodel import Session, select


def _stylebook_canonical_label(
    session: Session,
    *,
    stylebook_id: int,
    model: type,
    canonical_id: str,
) -> str | None:
    row = session.exec(
        select(model).where(
            model.id == canonical_id,  # type: ignore[attr-defined]
            model.stylebook_id == stylebook_id,  # type: ignore[attr-defined]
        )
    ).first()
    if row is None:
        return None
    label = (getattr(row, "label", None) or "").strip()
    return label or None


def public_canonical_label(
    session: Session,
    *,
    stylebook_id: int,
    entity_type: str,
    entity_id: str,
) -> str | None:
    eid = entity_id.strip()
    if entity_type == "location":
        return _stylebook_canonical_label(
            session,
            stylebook_id=stylebook_id,
            model=StylebookLocationCanonical,
            canonical_id=eid,
        )
    if entity_type == "person":
        return _stylebook_canonical_label(
            session,
            stylebook_id=stylebook_id,
            model=StylebookPersonCanonical,
            canonical_id=eid,
        )
    if entity_type == "organization":
        return _stylebook_canonical_label(
            session,
            stylebook_id=stylebook_id,
            model=StylebookOrganizationCanonical,
            canonical_id=eid,
        )
    if entity_type == "work":
        try:
            UUID(eid)
        except ValueError:
            return None
        return f"Work {eid[:8]}"
    return None
