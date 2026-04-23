"""Pure + session-backed policy: when to link, materialize, or defer Stylebook canonicals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical, SubstrateLocation
from sqlmodel import Session, select

from backfield_stylebook.canonical_match_score import (
    AUTOLINK_MIN_SCORE,
    RECALL_MIN_SCORE,
    CanonicalMatchFeatures,
    SubstrateMatchInput,
    _loose_key,
    classify_recall_score,
    policy_match_score,
)
from backfield_stylebook.canonical_retrieval import (
    load_canonical_match_features,
    retrieve_candidate_canonical_ids,
)
from backfield_stylebook.place_extract_location_types import (
    ADDRESS_PLACE_KIND_PRIVATE_RESIDENCE,
    ADDRESS_PLACE_KIND_PUBLIC_NAMED,
    ADDRESS_PLACE_KIND_UNKNOWN,
    is_address_like_location_type,
)


class CanonicalPersistDecision(StrEnum):
    DEFER = "defer"
    LINK_EXISTING = "link_existing"
    MATERIALIZE_NEW = "materialize_new"


@dataclass(frozen=True)
class CanonicalPersistPlan:
    decision: CanonicalPersistDecision
    """When ``LINK_EXISTING``, the canonical row id to attach."""

    existing_canonical_id: int | None = None
    """Structured audit trail persisted on ``SubstrateLocation.canonical_review_reasons_json``."""

    resolution_reasons: tuple[dict[str, Any], ...] = ()


def find_existing_canonical_id_by_alias(
    session: Session,
    *,
    stylebook_id: int,
    normalized_name: str,
) -> int | None:
    """Return ``StylebookLocationCanonical.id`` if an alias matches in this Stylebook."""
    norm = str(normalized_name)
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
        .limit(1)
    )
    canon = session.exec(stmt).first()
    if canon is None or canon.id is None:
        return None
    return int(canon.id)


def _address_place_kind_from_entry(entry: dict[str, Any] | None) -> str:
    """Normalize PlaceExtract ``address_place_kind`` (default ``unknown``)."""
    if not isinstance(entry, dict):
        return ADDRESS_PLACE_KIND_UNKNOWN
    raw = entry.get("address_place_kind")
    s = str(raw).strip().lower() if raw is not None else ""
    if s in (
        ADDRESS_PLACE_KIND_PUBLIC_NAMED,
        ADDRESS_PLACE_KIND_PRIVATE_RESIDENCE,
        ADDRESS_PLACE_KIND_UNKNOWN,
    ):
        return s
    return ADDRESS_PLACE_KIND_UNKNOWN


def _should_defer(
    *,
    places_bucket: str,
    location: SubstrateLocation,
    entry: dict[str, Any] | None = None,
) -> bool:
    if places_bucket == "needs_review":
        return True
    st = str(location.status or "")
    if st in ("needs_review", "failed"):
        return True
    lt = (location.location_type or "").strip().lower()
    kind = _address_place_kind_from_entry(entry)
    if is_address_like_location_type(lt) and kind == ADDRESS_PLACE_KIND_PRIVATE_RESIDENCE:
        return True
    if lt == "address" and kind != ADDRESS_PLACE_KIND_PUBLIC_NAMED:
        return True
    return False


_NO_AUTOMATIC_CANONICAL_MATERIALIZATION_TYPES: frozenset[str] = frozenset(
    {
        "address",
        "intersection_highway",
        "intersection_road",
        "street_road",
    }
)

# Ordered from broadest to most specific.  When the canonical's ``location_type`` belongs to one
# of these groups the substrate must belong to the **same** group; a city canonical cannot absorb
# an address substrate, and vice-versa.  Types absent from every group (address, place, point,
# intersection_*, region_city, natural, other, …) are "flexible" and may cross-match each other.
_STRICT_TYPE_GROUPS: tuple[frozenset[str], ...] = (
    frozenset({"country", "region_national"}),
    frozenset({"state", "region_state"}),
    frozenset({"county"}),
    frozenset({"city", "town"}),
    frozenset({"neighborhood", "community_area", "district", "borough", "suburb", "village"}),
)


def _type_group_for(location_type: str | None) -> frozenset[str] | None:
    """Return the strict group for ``location_type``, or ``None`` if it is flexible."""
    lt = (location_type or "").strip().lower()
    for group in _STRICT_TYPE_GROUPS:
        if lt in group:
            return group
    return None


def types_are_autolink_compatible(
    substrate_lt: str | None,
    canonical_lt: str | None,
) -> bool:
    """Return ``False`` when a strict type mismatch should block autolink (and ambiguous) tiers.

    If the canonical belongs to a strict group (city, county, state, neighborhood, …) the
    substrate must be in the **same** group.  Flexible types (address, place, intersection, ward,
    etc.) are never gated against each other; they can also match canonicals with no type set.
    If the substrate type is absent (``None`` / empty) the gate cannot apply and the link
    is allowed.  A substrate with a *known* flexible type (address, place, intersection, ward,
    etc.) is blocked from autolinking to a strict-group canonical: e.g. an address must not
    link to a city canonical just because the city name appears as a tail in its name.
    """
    canonical_group = _type_group_for(canonical_lt)
    if canonical_group is None:
        return True  # canonical has no type or a flexible type → no gate
    if not (substrate_lt or "").strip():
        return True  # substrate type is unknown → can't determine incompatibility
    substrate_group = _type_group_for(substrate_lt)
    if substrate_group is None:
        # Substrate has a known flexible type (not in any strict group) and the canonical
        # is in a strict group → incompatible.
        return False
    return substrate_group is canonical_group


# When the display name has a multi-token head (e.g. ``West Ridge, Chicago, IL``), require every
# such token to appear on the candidate label/aliases before allowing autolink-tier scores. This
# blocks ``… Chicago, IL`` child places from fuzzy-autolinking to a bare ``Chicago, IL`` canonical
# via token-coverage / long-formatted-address overlap (non-address scoring is string-only—no
# geometry involved).
_HEAD_ANCHOR_GATED_TYPES: frozenset[str] = frozenset(
    {
        "neighborhood",
        "city",
        "town",
        "village",
        "district",
        "ward",
        "community_area",
        "borough",
        "suburb",
        "county",
        # POI / school / etc. (PlaceExtract ``place``): name still carries ``..., City, ST`` and
        # string-only fuzzy scoring can otherwise autolink to the city canonical.
        "place",
        "point",
    }
)


def _location_type_allows_autocreate_without_strict_geometry(location_type: str | None) -> bool:
    lt = (location_type or "").strip().lower()
    if lt in _NO_AUTOMATIC_CANONICAL_MATERIALIZATION_TYPES:
        return False
    if "span" in lt:
        return False
    return True


def _should_apply_head_anchor_gate(location_type: str | None) -> bool:
    lt = (location_type or "").strip().lower()
    if lt == "address" or lt in _NO_AUTOMATIC_CANONICAL_MATERIALIZATION_TYPES:
        return False
    return lt in _HEAD_ANCHOR_GATED_TYPES


def _head_anchor_tokens(display_name: str) -> list[str]:
    first = display_name.split(",")[0].strip()
    if not first:
        return []
    return [t for t in _loose_key(first).split() if len(t) >= 3]


def _head_anchor_gate_passes(display_name: str, candidate: CanonicalMatchFeatures) -> bool:
    tokens = _head_anchor_tokens(display_name)
    if len(tokens) < 2:
        return True
    blob = _loose_key(candidate.label)
    for a in candidate.normalized_aliases:
        blob += " " + _loose_key(a)
    return all(t in blob for t in tokens)


def _match_basis_for_audit(location_type: str | None) -> str:
    if (location_type or "").strip().lower() == "address":
        return "string_and_point_geometry"
    return "string_only"


def _should_materialize_new_strict(location: SubstrateLocation) -> bool:
    """Legacy gate for excluded types: only materialize with resolved geocode + geometry."""
    if location.geometry_json is None:
        return False
    if str(location.status or "") != "resolved":
        return False
    return True


def rank_scored_canonical_recall_matches(
    session: Session,
    *,
    location: SubstrateLocation,
    recall: list[tuple[int, str]],
) -> list[tuple[int, str, float, int]]:
    """Score each recalled canonical; return best-first rows.

    Each tuple is ``(canonical_id, label, score, recall_index)``. Tie-break on equal
    ``score``: higher ``recall_index`` wins, matching fuzzy ``best_id`` selection in
    :func:`decide_canonical_persist_plan`.
    """
    if not recall:
        return []
    cids = [cid for cid, _ in recall]
    bundles = load_canonical_match_features(session, canonical_ids=cids)
    substrate = SubstrateMatchInput(
        name=str(location.name),
        normalized_name=str(location.normalized_name),
        geometry_json=location.geometry_json,
        formatted_address=location.formatted_address,
    )
    rows: list[tuple[int, int, str, float]] = []
    for recall_index, (canon_id, hint) in enumerate(recall):
        row = bundles.get(canon_id)
        if row is None:
            continue
        canon, alias_tup = row
        feat = CanonicalMatchFeatures(
            canonical_id=canon_id,
            label=str(canon.label),
            normalized_aliases=alias_tup,
            geometry_json=canon.geometry_json,
            retrieval_string_hint=hint,
        )
        sc = float(
            policy_match_score(
                substrate,
                feat,
                substrate_location_type=location.location_type,
            )
        )
        gate_lt = _should_apply_head_anchor_gate(location.location_type)
        if gate_lt and not _head_anchor_gate_passes(str(location.name), feat):
            sc = min(sc, RECALL_MIN_SCORE - 0.001)
        if not types_are_autolink_compatible(location.location_type, canon.location_type):
            sc = min(sc, RECALL_MIN_SCORE - 0.001)
        rows.append((recall_index, int(canon_id), str(canon.label), sc))
    rows.sort(key=lambda r: (-r[3], -r[0]))
    return [(r[1], r[2], r[3], r[0]) for r in rows]


def _should_materialize_when_no_canonical_match(location: SubstrateLocation) -> bool:
    """After exact match + fuzzy tiers: whether to create a new canonical.

    Most location types get a canonical when nothing linked and recall is not ambiguous,
    as long as the row is not a hard geocode failure and has a normalized name.

    Address, intersections, and span / street-road types keep the strict geometry rule.
    """
    if _location_type_allows_autocreate_without_strict_geometry(location.location_type):
        st = str(location.status or "")
        if st == "failed":
            return False
        if not str(location.normalized_name or "").strip():
            return False
        return True
    return _should_materialize_new_strict(location)


def substrate_may_materialize_canonical_after_recall(location: SubstrateLocation) -> bool:
    """True when ``MATERIALIZE_NEW`` is allowed for this row (same gates as rules materialize).

    Used when LLM adjudication declines linking to any recalled canonical so the plan can
    still suggest creating a new canonical (e.g. Austin, AR vs Austin, TX).
    """
    return _should_materialize_when_no_canonical_match(location)


def decide_canonical_persist_plan(
    session: Session,
    *,
    stylebook_id: int,
    places_bucket: str,
    location: SubstrateLocation,
    entry: dict[str, Any],
) -> CanonicalPersistPlan:
    """Decide how persistence should treat Stylebook canonicalization for this substrate row.

    ``entry`` carries PlaceExtract extras (e.g. ``address_place_kind``) for address deferral rules.
    """
    if _should_defer(places_bucket=places_bucket, location=location, entry=entry):
        lt = (location.location_type or "").strip().lower()
        kind = _address_place_kind_from_entry(entry)
        if is_address_like_location_type(lt) and kind == ADDRESS_PLACE_KIND_PRIVATE_RESIDENCE:
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.DEFER,
                resolution_reasons=(
                    {
                        "code": "private_place_or_residence",
                        "message": "Private place or residence",
                        "location_type": location.location_type,
                        "places_bucket": places_bucket,
                        "substrate_status": str(location.status or ""),
                    },
                ),
            )
        return CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=defer_reason_payload(places_bucket=places_bucket, location=location),
        )

    cid = find_existing_canonical_id_by_alias(
        session, stylebook_id=stylebook_id, normalized_name=str(location.normalized_name)
    )
    if cid is not None:
        alias_canon = session.get(StylebookLocationCanonical, cid)
        alias_canon_lt = alias_canon.location_type if alias_canon is not None else None
        if types_are_autolink_compatible(location.location_type, alias_canon_lt):
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.LINK_EXISTING,
                existing_canonical_id=cid,
                resolution_reasons=(
                    {
                        "code": "linked_exact_normalized_alias",
                        "canonical_id": int(cid),
                        "normalized_name": str(location.normalized_name),
                        "match_basis": "exact_alias_lookup",
                        "type_gate_applied": True,
                    },
                ),
            )
        # Type incompatible: fall through to fuzzy recall so the location can
        # materialize its own canonical rather than inheriting the wrong one.

    recall = retrieve_candidate_canonical_ids(
        session,
        stylebook_id=stylebook_id,
        query_text=str(location.name),
        normalized_query=str(location.normalized_name),
        formatted_address=location.formatted_address,
    )
    best_id: int | None = None
    best_score = 0.0
    recall_canonical_ids: tuple[int, ...] = ()
    if recall:
        recall_canonical_ids = tuple(int(cid) for cid, _ in recall)
        ranked = rank_scored_canonical_recall_matches(
            session, location=location, recall=list(recall)
        )
        if ranked:
            best_id, best_score = ranked[0][0], ranked[0][2]
        tier = classify_recall_score(best_score)
        if tier == "autolink" and best_id is not None:
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.LINK_EXISTING,
                existing_canonical_id=int(best_id),
                resolution_reasons=(
                    {
                        "code": "linked_fuzzy_autolink",
                        "canonical_id": int(best_id),
                        "best_score": float(best_score),
                        "autolink_min_score": float(AUTOLINK_MIN_SCORE),
                        "recall_min_score": float(RECALL_MIN_SCORE),
                        "match_basis": _match_basis_for_audit(location.location_type),
                        "head_anchor_gate_applied": _should_apply_head_anchor_gate(
                            location.location_type
                        ),
                        "type_gate_applied": True,
                        "recall_canonical_ids": list(recall_canonical_ids[:24]),
                    },
                ),
            )
        if tier == "ambiguous" and best_id is not None:
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.DEFER,
                resolution_reasons=(
                    {
                        "code": "ambiguous_canonical_match",
                        "best_canonical_id": int(best_id),
                        "best_score": float(best_score),
                        "autolink_min_score": float(AUTOLINK_MIN_SCORE),
                        "recall_min_score": float(RECALL_MIN_SCORE),
                        "match_basis": _match_basis_for_audit(location.location_type),
                        "head_anchor_gate_applied": _should_apply_head_anchor_gate(
                            location.location_type
                        ),
                        "type_gate_applied": True,
                        "recall_canonical_ids": list(recall_canonical_ids[:24]),
                    },
                ),
            )

    if _should_materialize_when_no_canonical_match(location):
        extra: dict[str, Any] = {}
        if recall_canonical_ids:
            extra["fuzzy_best_score_before_materialize"] = float(best_score)
            extra["fuzzy_recall_canonical_ids"] = list(recall_canonical_ids[:24])
        return CanonicalPersistPlan(
            decision=CanonicalPersistDecision.MATERIALIZE_NEW,
            resolution_reasons=(
                {
                    "code": "materialized_new_canonical",
                    "had_fuzzy_recall": bool(recall_canonical_ids),
                    "match_basis": _match_basis_for_audit(location.location_type),
                    "head_anchor_gate_applied": _should_apply_head_anchor_gate(
                        location.location_type
                    ),
                    **extra,
                },
            ),
        )

    return CanonicalPersistPlan(
        decision=CanonicalPersistDecision.DEFER,
        resolution_reasons=defer_reason_payload(
            places_bucket=places_bucket,
            location=location,
            extra_context={
                "fuzzy_best_score": float(best_score) if recall_canonical_ids else None,
                "fuzzy_recall_canonical_ids": list(recall_canonical_ids[:24])
                if recall_canonical_ids
                else None,
            },
        ),
    )


def plan_has_ambiguous_canonical_match(plan: CanonicalPersistPlan) -> bool:
    """True when rules deferred with an ambiguous fuzzy recall (LLM adjudication hook)."""
    for r in plan.resolution_reasons:
        if isinstance(r, dict) and str(r.get("code") or "") == "ambiguous_canonical_match":
            return True
    return False


def defer_reason_payload(
    *,
    places_bucket: str,
    location: SubstrateLocation,
    extra_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Structured reasons for ``canonical_review_reasons_json`` when deferring."""
    d: dict[str, Any] = {
        "code": "deferred_policy",
        "places_bucket": places_bucket,
        "substrate_status": str(location.status or ""),
        "location_type": location.location_type,
    }
    if extra_context:
        for k, v in extra_context.items():
            if v is not None:
                d[k] = v
    return (d,)
