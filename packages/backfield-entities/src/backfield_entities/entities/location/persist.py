"""Location canonical + alias persistence gated by canonical policy."""

from __future__ import annotations

from typing import Any

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical, SubstrateLocation
from sqlmodel import Session, select

from backfield_entities.activity import (
    EVENT_CANONICAL_CREATED,
    EVENT_SUBSTRATE_LINKED,
    log_stylebook_activity_safe,
)
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
from backfield_entities.canonical.plan_types import CanonicalPersistDecision, CanonicalPersistPlan
from backfield_entities.canonical.slug import (
    allocate_unique_canonical_slug,
    flush_new_canonical_with_slug_retry,
)
from backfield_entities.entities.location.policy import plan_has_ambiguous_canonical_match
from backfield_entities.entities.location.recall import location_alias_lookup_keys
from backfield_entities.geo.h3_index import apply_h3_fields
from backfield_entities.text.match_normalize import normalize_match_text


def _h3_field_kwargs(
    *,
    geometry_json: dict[str, Any] | None,
    h3_cell: str | None = None,
    h3_resolution: int | None = None,
) -> dict[str, Any]:
    cell, resolution = apply_h3_fields(
        h3_cell=h3_cell,
        h3_resolution=h3_resolution,
        geometry_json=geometry_json,
    )
    return {"h3_cell": cell, "h3_resolution": resolution}


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
    return normalize_match_text(text)


def normalized_alias_variants(normalized_alias: str) -> tuple[str, ...]:
    """Stable variants for recall/exact matching (accent, apostrophe, loose key)."""
    return location_alias_lookup_keys(normalized_alias)


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
    for norm in normalized_alias_variants(_normalize_alias_text(clean)):
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
    for norm in normalized_alias_variants(str(location.normalized_name)):
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
    if provenance == "substrate_ingest":
        # Linked rows can outlive the decision that set their FK; revalidate before
        # refreshing machine aliases so stale links cannot poison future exact recall.
        from backfield_entities.canonical.link_commit_gate import sync_link_commit_blocked

        veto = sync_link_commit_blocked(
            session,
            entity_type="location",
            substrate_row=location,
            canonical_id=canon_id,
            stylebook_id=stylebook_id,
        )
        if veto is not None:
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
    if provenance == "substrate_ingest":
        # This is the final write boundary; callers may arrive from rules, cache, or LLM.
        from backfield_entities.canonical.link_commit_gate import sync_link_commit_blocked

        veto = sync_link_commit_blocked(
            session,
            entity_type="location",
            substrate_row=location,
            canonical_id=str(canonical_id),
            stylebook_id=stylebook_id,
        )
        if veto is not None:
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
    def _build_row(slug: str) -> StylebookLocationCanonical:
        return StylebookLocationCanonical(
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
            **_h3_field_kwargs(geometry_json=gj),
        )

    canon = flush_new_canonical_with_slug_retry(
        session,
        stylebook_id=stylebook_id,
        label=clean,
        allocate_slug=lambda sess, sb_id, lbl: allocate_unique_canonical_slug(
            sess, stylebook_id=sb_id, label=lbl
        ),
        build_row=_build_row,
    )
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
    source_details = (
        location.source_details_json if isinstance(location.source_details_json, dict) else {}
    )
    if str(location.status or "").strip().lower() in {"failed", "needs_review"} or str(
        source_details.get("places_bucket") or ""
    ).strip().lower() == "needs_review":
        raise ValueError("rejected or review-required geocode cannot materialize a canonical")
    gj = location.geometry_json
    lt = (location.location_type or "").strip().lower() or None
    fa = (location.formatted_address or "").strip() or None
    comps = place_extract_components_from_entry(location, None)
    jur = stylebook_jurisdiction_fields_from_components(comps)
    dfields = stylebook_district_fields_from_components(comps)
    label = str(location.name)

    def _build_row(slug: str) -> StylebookLocationCanonical:
        return StylebookLocationCanonical(
            stylebook_id=stylebook_id,
            label=label,
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
            **_h3_field_kwargs(
                geometry_json=dict(gj) if isinstance(gj, dict) else gj,
                h3_cell=location.h3_cell,
                h3_resolution=location.h3_resolution,
            ),
        )

    canon = flush_new_canonical_with_slug_retry(
        session,
        stylebook_id=stylebook_id,
        label=label,
        allocate_slug=lambda sess, sb_id, lbl: allocate_unique_canonical_slug(
            sess, stylebook_id=sb_id, label=lbl
        ),
        build_row=_build_row,
    )
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


def _adjudication_item_from_plan(plan: CanonicalPersistPlan) -> dict[str, Any] | None:
    for r in plan.resolution_reasons:
        if isinstance(r, dict) and str(r.get("code") or "") == "canonical_adjudication":
            return dict(r)
    return None


def _canonical_suggestion_from_adjudication(
    adj: dict[str, Any],
    *,
    source: str = "canonical_adjudication",
) -> dict[str, Any] | None:
    outcome = str(adj.get("outcome") or "").strip()
    src = str(adj.get("source") or source)
    if outcome == "link_existing":
        cid = adj.get("canonical_id")
        if cid is not None and str(cid).strip():
            return {
                "code": "canonical_suggestion",
                "source": src,
                "suggested_action": "link_existing",
                "stylebook_location_canonical_id": str(cid).strip(),
            }
    if outcome == "no_high_confidence_link":
        return {
            "code": "canonical_suggestion",
            "source": src,
            "suggested_action": "materialize_new",
        }
    return None


def _canonical_suggestion_from_rules_plan(plan: CanonicalPersistPlan) -> dict[str, Any] | None:
    """Structured hint for Stylebook review UI when auto-apply is off."""
    adj = _adjudication_item_from_plan(plan)
    if adj is not None:
        from_adj = _canonical_suggestion_from_adjudication(adj)
        if from_adj is not None:
            return from_adj
    if plan.decision == CanonicalPersistDecision.DEFER and (
        plan_has_ambiguous_canonical_match(plan) and adj is None
    ):
        return None
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


CANDIDATE_AI_REVIEW_SOURCE = "candidate_ai_review"


def apply_candidate_ai_review_recommendation(
    session: Session,
    *,
    location: SubstrateLocation,
    plan: CanonicalPersistPlan,
) -> bool:
    if str(location.canonical_link_status) != CANONICAL_LINK_PENDING:
        return False
    if location.stylebook_location_canonical_id is not None:
        return False
    raw = location.canonical_review_reasons_json
    reasons: list[dict[str, Any]] = []
    if isinstance(raw, list):
        reasons = [dict(r) for r in raw if isinstance(r, dict)]
    elif isinstance(raw, dict):
        reasons = [dict(raw)]
    reasons = [
        r
        for r in reasons
        if str(r.get("code") or "") not in ("canonical_suggestion", "canonical_adjudication")
    ]
    for r in plan.resolution_reasons:
        if isinstance(r, dict):
            reasons.append(dict(r))
    extra = _canonical_suggestion_from_rules_plan(plan)
    has_suggestion = False
    if extra is not None:
        suggestion = dict(extra)
        suggestion["source"] = CANDIDATE_AI_REVIEW_SOURCE
        reasons.append(suggestion)
        has_suggestion = True
    location.canonical_review_reasons_json = reasons
    session.add(location)
    return has_suggestion


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
    has_suggestion = any(
        isinstance(r, dict) and str(r.get("code") or "") == "canonical_suggestion" for r in reasons
    )
    extra = _canonical_suggestion_from_rules_plan(plan)
    if extra is not None and not has_suggestion:
        reasons.append(extra)
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
        if provenance == "substrate_ingest":
            from backfield_entities.canonical.link_commit_gate import gate_or_coerce_link_plan

            gated = gate_or_coerce_link_plan(
                session,
                plan,
                entity_type="location",
                substrate_row=location,
                stylebook_id=stylebook_id,
            )
            if gated.decision != CanonicalPersistDecision.LINK_EXISTING:
                apply_canonical_persist_plan(
                    session,
                    stylebook_id=stylebook_id,
                    location=location,
                    plan=gated,
                    places_bucket=places_bucket,
                    provenance=provenance,
                    auto_apply_canonicalization=auto_apply_canonicalization,
                )
                return
        link_to_existing_canonical(
            session,
            stylebook_id=stylebook_id,
            location=location,
            canonical_id=str(plan.existing_canonical_id),
            provenance=provenance,
            audit_reasons=reasons,
        )
        log_stylebook_activity_safe(
            session,
            stylebook_id=stylebook_id,
            project_id=int(location.project_id),
            actor_type="system",
            source="ingest_pipeline",
            event_type=EVENT_SUBSTRATE_LINKED,
            entity_type="location",
            entity_id=str(location.id) if location.id is not None else None,
            entity_label=str(location.name),
            related_entity_type="location",
            related_entity_id=str(plan.existing_canonical_id),
            payload_json={"provenance": provenance},
        )
        return
    materialize_new_canonical_and_link(
        session,
        stylebook_id=stylebook_id,
        location=location,
        provenance=provenance,
        audit_reasons=reasons,
    )
    log_stylebook_activity_safe(
        session,
        stylebook_id=stylebook_id,
        project_id=int(location.project_id),
        actor_type="system",
        source="ingest_pipeline",
        event_type=EVENT_CANONICAL_CREATED,
        entity_type="location",
        entity_id=str(location.stylebook_location_canonical_id)
        if location.stylebook_location_canonical_id is not None
        else None,
        entity_label=str(location.name),
        related_entity_type="location",
        related_entity_id=str(location.id) if location.id is not None else None,
        payload_json={"provenance": provenance, "materialized_from_substrate": True},
    )
