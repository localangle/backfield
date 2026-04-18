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
    """Ensure a canonical row + alias exist for this substrate location within the Stylebook.

    Canonical and substrate remain separate objects: this helper does **not** set
    ``SubstrateLocation.stylebook_location_canonical_id`` — editorial linking uses that FK.

    When the substrate row is not yet linked, reuse a ``StylebookLocationCanonical`` that
    already has an alias with the same ``normalized_name`` in this Stylebook (dedupe on
    ingest); otherwise create a new canonical. Legacy ``primary_substrate_location_id`` is
    not used for lookup or new writes.
    """
    if location.id is None:
        return

    norm = str(location.normalized_name)

    if location.stylebook_location_canonical_id is not None:
        canon_id = int(location.stylebook_location_canonical_id)
        canon = session.get(StylebookLocationCanonical, canon_id)
        if canon is None or int(canon.stylebook_id) != int(stylebook_id):
            return
    else:
        stmt = (
            select(StylebookLocationCanonical)
            .join(
                StylebookLocationAlias,
                StylebookLocationAlias.location_canonical_id == StylebookLocationCanonical.id,
            )
            .where(
                StylebookLocationCanonical.stylebook_id == stylebook_id,
                StylebookLocationAlias.normalized_alias == norm,
            )
        )
        canon = session.exec(stmt).first()
        if canon is None:
            canon = StylebookLocationCanonical(
                stylebook_id=stylebook_id,
                label=str(location.name),
                primary_substrate_location_id=None,
                status="active",
            )
            session.add(canon)
            session.flush()
        canon_id = int(canon.id)  # type: ignore[arg-type]

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
