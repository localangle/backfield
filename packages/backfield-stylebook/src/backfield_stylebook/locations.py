"""Location canonical + alias persistence gated by canonical policy."""

from __future__ import annotations

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical, SubstrateLocation
from sqlmodel import Session, select

from backfield_stylebook.canonical_link import CANONICAL_LINK_LINKED, CANONICAL_LINK_PENDING
from backfield_stylebook.canonical_policy import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
    defer_reason_payload,
)


def assert_canonical_link_invariant(location: SubstrateLocation) -> None:
    """Debug invariant: ``linked`` iff FK set; other statuses require null FK."""
    if location.canonical_link_status == CANONICAL_LINK_LINKED:
        if location.stylebook_location_canonical_id is None:
            raise AssertionError(
                "canonical_link_status=linked requires stylebook_location_canonical_id"
            )
    else:
        if location.stylebook_location_canonical_id is not None:
            raise AssertionError(
                f"canonical_link_status={location.canonical_link_status!r} requires null "
                "stylebook_location_canonical_id"
            )


def _upsert_alias_for_canonical(
    session: Session,
    *,
    canon_id: int,
    location: SubstrateLocation,
    provenance: str,
) -> None:
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


def refresh_aliases_for_linked_location(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
    provenance: str = "substrate_ingest",
) -> None:
    """Upsert alias for a substrate row that already has ``stylebook_location_canonical_id``."""
    if location.id is None or location.stylebook_location_canonical_id is None:
        return
    canon_id = int(location.stylebook_location_canonical_id)
    canon = session.get(StylebookLocationCanonical, canon_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        return
    _upsert_alias_for_canonical(
        session,
        canon_id=canon_id,
        location=location,
        provenance=provenance,
    )


def link_to_existing_canonical(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
    canonical_id: int,
    provenance: str = "substrate_ingest",
) -> None:
    """Attach substrate row to an existing canonical and upsert alias."""
    if location.id is None:
        return
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        return
    location.stylebook_location_canonical_id = int(canon.id)  # type: ignore[arg-type]
    location.canonical_link_status = CANONICAL_LINK_LINKED
    location.canonical_review_reasons_json = None
    session.add(location)
    session.flush()
    cid = int(canon.id)  # type: ignore[arg-type]
    _upsert_alias_for_canonical(
        session,
        canon_id=cid,
        location=location,
        provenance=provenance,
    )


def materialize_new_canonical_and_link(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
    provenance: str = "substrate_ingest",
) -> None:
    """Create a new canonical, set FK + ``linked``, upsert alias."""
    if location.id is None:
        return
    gj = location.geometry_json
    canon = StylebookLocationCanonical(
        stylebook_id=stylebook_id,
        label=str(location.name),
        primary_substrate_location_id=None,
        status="active",
        geometry_json=dict(gj) if isinstance(gj, dict) else gj,
        geometry_type=location.geometry_type,
        geometry=location.geometry,
    )
    session.add(canon)
    session.flush()
    cid = int(canon.id)  # type: ignore[arg-type]
    location.stylebook_location_canonical_id = cid
    location.canonical_link_status = CANONICAL_LINK_LINKED
    location.canonical_review_reasons_json = None
    session.add(location)
    session.flush()
    _upsert_alias_for_canonical(
        session,
        canon_id=cid,
        location=location,
        provenance=provenance,
    )


def apply_canonical_persist_plan(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
    plan: CanonicalPersistPlan,
    places_bucket: str,
    provenance: str = "substrate_ingest",
) -> None:
    """Apply policy outcome: defer (pending, no Stylebook rows), link, or materialize."""
    if plan.decision == CanonicalPersistDecision.DEFER:
        location.canonical_link_status = CANONICAL_LINK_PENDING
        if plan.defer_review_reasons is not None:
            location.canonical_review_reasons_json = [dict(r) for r in plan.defer_review_reasons]
        else:
            location.canonical_review_reasons_json = defer_reason_payload(
                places_bucket=places_bucket, location=location
            )
        session.add(location)
        return
    if plan.decision == CanonicalPersistDecision.LINK_EXISTING:
        if plan.existing_canonical_id is None:
            return
        link_to_existing_canonical(
            session,
            stylebook_id=stylebook_id,
            location=location,
            canonical_id=int(plan.existing_canonical_id),
            provenance=provenance,
        )
        return
    materialize_new_canonical_and_link(
        session, stylebook_id=stylebook_id, location=location, provenance=provenance
    )


def sync_substrate_location_into_stylebook(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
    provenance: str = "substrate_ingest",
) -> None:
    """Backward-compatible entry: refresh aliases when already linked; no-op otherwise.

    Prefer :func:`apply_canonical_persist_plan` from persistence after policy.
    """
    if location.stylebook_location_canonical_id is not None:
        refresh_aliases_for_linked_location(
            session, stylebook_id=stylebook_id, location=location, provenance=provenance
        )
