"""Location canonical + alias materialization from substrate rows."""

from __future__ import annotations

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical, SubstrateLocation
from sqlmodel import Session, select


def sync_substrate_location_into_stylebook(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
    provenance: str = "substrate_ingest",
) -> None:
    """Ensure a canonical row + alias exist for this substrate location within the Stylebook."""
    if location.id is None:
        return

    loc_id = int(location.id)
    canon = session.exec(
        select(StylebookLocationCanonical).where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
            StylebookLocationCanonical.primary_substrate_location_id == loc_id,
        )
    ).first()
    if canon is None:
        canon = StylebookLocationCanonical(
            stylebook_id=stylebook_id,
            label=str(location.name),
            primary_substrate_location_id=loc_id,
            status="active",
        )
        session.add(canon)
        session.flush()
    elif canon.primary_substrate_location_id is None:
        canon.primary_substrate_location_id = loc_id
        session.add(canon)
        session.flush()

    canon_id = int(canon.id)  # type: ignore[arg-type]
    norm = str(location.normalized_name)
    existing = session.exec(
        select(StylebookLocationAlias).where(
            StylebookLocationAlias.location_canonical_id == canon_id,
            StylebookLocationAlias.normalized_alias == norm,
        )
    ).first()
    if existing is None:
        session.add(
            StylebookLocationAlias(
                location_canonical_id=canon_id,
                alias_text=str(location.name),
                normalized_alias=norm,
                provenance=provenance,
                suppressed=False,
            )
        )
    else:
        existing.alias_text = str(location.name)
        existing.provenance = provenance
        existing.suppressed = False
        session.add(existing)
