"""Location canonical + alias persistence gated by canonical policy."""

from __future__ import annotations

from typing import Any

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical, SubstrateLocation
from sqlmodel import Session, select

from backfield_entities.canonical.jurisdiction import (
    place_extract_components_from_entry,
    stylebook_district_fields_from_components,
    stylebook_jurisdiction_fields_from_components,
)
from backfield_entities.canonical.link import (
    CANONICAL_LINK_LINKED,
    CANONICAL_LINK_PENDING,
    CANONICAL_LINK_WAIVED,
)
from backfield_entities.canonical.match_score import _loose_key
from backfield_entities.canonical.plan_types import CanonicalPersistDecision, CanonicalPersistPlan
from backfield_entities.canonical.slug import allocate_unique_canonical_slug


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


def _normalize_alias_text(text: str) -> str:
    return text.strip().lower()


def _normalized_alias_variants(normalized_alias: str) -> tuple[str, ...]:
    """Stable variants for recall/exact matching.

    We keep this conservative: only add an ordinal-stripped form so that strings like
    ``15th Ward`` and ``Ward 15`` share more overlap in recall.
    """
    norm = str(normalized_alias).strip().lower()
    if not norm:
        return ()
    # Use the same ordinal normalization as the scorer's loose-key path.
    stripped = _loose_key(norm)
    if stripped and stripped != norm:
        return (norm, stripped)
    return (norm,)


def seed_aliases_for_canonical_label(
    session: Session,
    *,
    canon_id: str,
    label: str,
    provenance: str,
) -> None:
    """Upsert normalized alias variants from a canonical label (import / manual create)."""
    clean = label.strip()
    if not clean:
        return
    for norm in _normalized_alias_variants(_normalize_alias_text(clean)):
        upsert_alias_for_canonical_text(
            session,
            canon_id=canon_id,
            alias_text=clean,
            normalized_alias=norm,
            provenance=provenance,
        )


def upsert_alias_for_canonical_text(
    session: Session,
    *,
    canon_id: str,
    alias_text: str,
    normalized_alias: str,
    provenance: str,
) -> None:
    norm = str(normalized_alias)
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
                alias_text=str(alias_text),
                normalized_alias=norm,
                provenance=provenance,
                suppressed=False,
            )
        )
    else:
        existing.alias_text = str(alias_text)
        existing.provenance = provenance
        existing.suppressed = False
        session.add(existing)


def _upsert_alias_for_canonical(
    session: Session,
    *,
    canon_id: str,
    location: SubstrateLocation,
    provenance: str,
) -> None:
    for norm in _normalized_alias_variants(str(location.normalized_name)):
        upsert_alias_for_canonical_text(
            session,
            canon_id=canon_id,
            alias_text=str(location.name),
            normalized_alias=norm,
            provenance=provenance,
        )


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
    canon_id = str(location.stylebook_location_canonical_id)
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
    canonical_id: str,
    provenance: str = "substrate_ingest",
    audit_reasons: list[dict[str, Any]] | None = None,
) -> None:
    """Attach substrate row to an existing canonical and upsert alias."""
    if location.id is None:
        return
    canon = session.get(StylebookLocationCanonical, canonical_id)
    if canon is None or int(canon.stylebook_id) != int(stylebook_id):
        return
    location.stylebook_location_canonical_id = str(canon.id)
    location.canonical_link_status = CANONICAL_LINK_LINKED
    location.canonical_review_reasons_json = (
        [dict(r) for r in audit_reasons] if audit_reasons is not None else None
    )
    session.add(location)
    session.flush()
    cid = str(canon.id)
    _upsert_alias_for_canonical(
        session,
        canon_id=cid,
        location=location,
        provenance=provenance,
    )


def create_standalone_canonical(
    session: Session,
    *,
    stylebook_id: int,
    label: str,
    location_type: str | None = None,
    formatted_address: str | None = None,
    geometry_json: dict[str, Any] | None = None,
    provenance: str = "stylebook_ui_manual",
) -> StylebookLocationCanonical:
    """Create a Stylebook canonical + primary alias without a ``SubstrateLocation`` row."""
    clean = label.strip()
    if not clean:
        raise ValueError("label is required")
    gj = dict(geometry_json) if isinstance(geometry_json, dict) else None
    gt_raw = gj.get("type") if isinstance(gj, dict) else None
    geometry_type_str = str(gt_raw) if gt_raw is not None else None
    lt = (location_type or "").strip().lower() or None
    fa = (formatted_address or "").strip() or None
    slug = allocate_unique_canonical_slug(session, stylebook_id=stylebook_id, label=clean)
    canon = StylebookLocationCanonical(
        stylebook_id=stylebook_id,
        label=clean,
        slug=slug,
        location_type=lt,
        formatted_address=fa,
        primary_substrate_location_id=None,
        status="active",
        geometry_json=gj,
        geometry_type=geometry_type_str,
        geometry=None,
    )
    session.add(canon)
    session.flush()
    cid = str(canon.id)
    seed_aliases_for_canonical_label(
        session, canon_id=cid, label=clean, provenance=provenance
    )
    session.flush()
    return canon


def materialize_new_canonical_and_link(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
    provenance: str = "substrate_ingest",
    audit_reasons: list[dict[str, Any]] | None = None,
) -> None:
    """Create a new canonical, set FK + ``linked``, upsert alias."""
    if location.id is None:
        return
    gj = location.geometry_json
    lt = (location.location_type or "").strip().lower() or None
    fa = (location.formatted_address or "").strip() or None
    slug = allocate_unique_canonical_slug(
        session, stylebook_id=stylebook_id, label=str(location.name)
    )
    comps = place_extract_components_from_entry(location, None)
    jur = stylebook_jurisdiction_fields_from_components(comps)
    dfields = stylebook_district_fields_from_components(comps)
    canon = StylebookLocationCanonical(
        stylebook_id=stylebook_id,
        label=str(location.name),
        slug=slug,
        location_type=lt,
        formatted_address=fa,
        primary_substrate_location_id=None,
        status="active",
        geometry_json=dict(gj) if isinstance(gj, dict) else gj,
        geometry_type=location.geometry_type,
        geometry=location.geometry,
        country_code=jur["country_code"],
        subdivision_code=jur["subdivision_code"],
        city_name=jur["city_name"],
        district_kind=dfields["district_kind"],
        district_number=dfields["district_number"],
        district_key=dfields["district_key"],
    )
    session.add(canon)
    session.flush()
    cid = str(canon.id)
    location.stylebook_location_canonical_id = cid
    location.canonical_link_status = CANONICAL_LINK_LINKED
    location.canonical_review_reasons_json = (
        [dict(r) for r in audit_reasons] if audit_reasons is not None else None
    )
    session.add(location)
    session.flush()
    _upsert_alias_for_canonical(
        session,
        canon_id=cid,
        location=location,
        provenance=provenance,
    )


def _resolution_includes_private_place_or_residence(plan: CanonicalPersistPlan) -> bool:
    for r in plan.resolution_reasons:
        if isinstance(r, dict) and str(r.get("code") or "") == "private_place_or_residence":
            return True
    return False


def _canonical_suggestion_from_rules_plan(plan: CanonicalPersistPlan) -> dict[str, Any] | None:
    """Structured hint for Stylebook review UI when auto-apply is off."""
    if (
        plan.decision == CanonicalPersistDecision.LINK_EXISTING
        and plan.existing_canonical_id is not None
    ):
        return {
            "code": "canonical_suggestion",
            "source": "rules_plan",
            "suggested_action": "link_existing",
            "stylebook_location_canonical_id": str(plan.existing_canonical_id),
        }
    if plan.decision == CanonicalPersistDecision.MATERIALIZE_NEW:
        return {
            "code": "canonical_suggestion",
            "source": "rules_plan",
            "suggested_action": "materialize_new",
        }
    if plan.decision == CanonicalPersistDecision.DEFER:
        return {
            "code": "canonical_suggestion",
            "source": "rules_plan",
            "suggested_action": "defer",
        }
    return None


def apply_canonical_persist_plan_review_only(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
    plan: CanonicalPersistPlan,
    places_bucket: str,
) -> None:
    """Queue for review: pending, no Stylebook FK, with reasons and optional suggestion."""
    _ = places_bucket
    _ = stylebook_id
    reasons: list[dict[str, Any]] = [dict(r) for r in plan.resolution_reasons]
    extra = _canonical_suggestion_from_rules_plan(plan)
    if extra is not None:
        reasons.append(extra)
    location.stylebook_location_canonical_id = None
    location.canonical_link_status = CANONICAL_LINK_PENDING
    location.canonical_review_reasons_json = reasons
    session.add(location)


def apply_canonical_persist_plan(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
    plan: CanonicalPersistPlan,
    places_bucket: str,
    provenance: str = "substrate_ingest",
    auto_apply_canonicalization: bool = False,
) -> None:
    """Apply policy outcome: defer (pending, no Stylebook rows), link, or materialize."""
    reasons = [dict(r) for r in plan.resolution_reasons]
    if plan.decision == CanonicalPersistDecision.DEFER:
        if auto_apply_canonicalization and _resolution_includes_private_place_or_residence(plan):
            location.canonical_link_status = CANONICAL_LINK_WAIVED
        else:
            location.canonical_link_status = CANONICAL_LINK_PENDING
        location.canonical_review_reasons_json = reasons
        session.add(location)
        return
    if plan.decision == CanonicalPersistDecision.LINK_EXISTING:
        if plan.existing_canonical_id is None:
            return
        link_to_existing_canonical(
            session,
            stylebook_id=stylebook_id,
            location=location,
            canonical_id=str(plan.existing_canonical_id),
            provenance=provenance,
            audit_reasons=reasons,
        )
        return
    materialize_new_canonical_and_link(
        session,
        stylebook_id=stylebook_id,
        location=location,
        provenance=provenance,
        audit_reasons=reasons,
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
