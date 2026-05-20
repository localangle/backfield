"""Pure + session-backed policy: when to link, materialize, or defer Stylebook canonicals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from backfield_db import StylebookLocationAlias, StylebookLocationCanonical, SubstrateLocation
from sqlmodel import Session, col, select

from backfield_stylebook.canonical_jurisdiction import (
    container_admin_query_from_components,
    district_identity_from_components,
    district_identity_key,
    geocode_components_vs_formatted_address_mismatch,
    geojson_bbox_centroid,
    geojson_bbox_diagonal_km,
    geojson_point_lon_lat,
    haversine_km,
    jurisdiction_from_components,
    place_extract_components_from_entry,
    point_in_geojson_bbox,
    strict_canonical_gates_enabled,
)
from backfield_stylebook.canonical_link_matrix import (
    autolink_container_to_fine_denied,
    link_pair_allowed,
    strict_type_group,
    types_are_comparable,
)
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
from backfield_stylebook.geocode_cache_resolve import try_resolve_substrate_location_cache_geometry
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

    existing_canonical_id: str | None = None
    """Structured audit trail persisted on ``SubstrateLocation.canonical_review_reasons_json``."""

    resolution_reasons: tuple[dict[str, Any], ...] = ()


def find_existing_canonical_id_by_alias(
    session: Session,
    *,
    stylebook_id: int,
    normalized_name: str,
) -> str | None:
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
    return str(canon.id)


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
    # Roadway spans are not auto-canonicalized; editors can link or create later from the queue.
    if lt == "span":
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

# Backwards-compatible name for :func:`link_pair_allowed` (type deny-list + product gates).
types_are_autolink_compatible = link_pair_allowed

# Recall demotion when an address point is far from a neighborhood polygon (pair is denied for
# autolink via :func:`link_pair_allowed`; this gate only affects comparable scoring paths).
ADDRESS_NEIGHBORHOOD_AUTOLINK_MAX_KM = 50.0


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
        # Corridors / lines / ward-scale buckets (PlaceExtract ``region_city``).
        "region_city",
        "natural",
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


_JURISDICTION_SCORE_GATE_SUBSTRATE_TYPES: frozenset[str] = frozenset(
    {
        "county",
        "city",
        "town",
        "village",
        "neighborhood",
        "community_area",
        "district",
        "borough",
        "suburb",
        "place",
        "point",
        "region_city",
        "address",
    }
)

_POI_LIKE_CANON_TYPES: frozenset[str] = frozenset({"place", "point", "address", "natural"})


def _jurisdiction_pair_demotes_recall_score(
    location: SubstrateLocation,
    canon: StylebookLocationCanonical,
    comps: dict[str, Any],
) -> bool:
    """True when structured jurisdictions disagree (per-candidate autolink gate)."""
    s_lt = (location.location_type or "").strip().lower()
    if s_lt not in _JURISDICTION_SCORE_GATE_SUBSTRATE_TYPES:
        return False
    s_country, s_sub, _city = jurisdiction_from_components(comps)
    if not s_sub:
        return False
    c_country = (canon.country_code or "").strip().upper()[:2] or None
    c_sub = (canon.subdivision_code or "").strip().upper()[:2] or None
    c_lt = (canon.location_type or "").strip().lower()
    if c_lt in _POI_LIKE_CANON_TYPES and not (c_country and c_sub):
        return False
    if c_sub and s_sub != c_sub:
        return True
    if c_country and s_country and s_country != c_country:
        return True
    return False


def _district_identity_pair_mismatch(
    substrate_comps: dict[str, Any],
    canon: StylebookLocationCanonical,
) -> bool:
    """True when both sides carry a full district key and they disagree."""
    sub_key = district_identity_key(district_identity_from_components(substrate_comps))
    if not sub_key:
        return False
    ck = (canon.district_key or "").strip()
    if not ck:
        return False
    return sub_key != ck


def _address_neighborhood_geometry_demotes_recall(
    location: SubstrateLocation,
    canon: StylebookLocationCanonical,
    feat: CanonicalMatchFeatures,
) -> bool:
    """Demote when address point is outside neighborhood bbox or too far from centroid."""
    lt = (location.location_type or "").strip().lower()
    c_lt = (canon.location_type or "").strip().lower()
    if lt != "address" or c_lt != "neighborhood":
        return False
    pt = geojson_point_lon_lat(
        location.geometry_json if isinstance(location.geometry_json, dict) else None
    )
    gj = feat.geometry_json if isinstance(feat.geometry_json, dict) else None
    if pt is None or gj is None:
        return False
    lon, lat = pt
    if not point_in_geojson_bbox(lon, lat, gj):
        return True
    cc = geojson_bbox_centroid(gj)
    if cc is None:
        return False
    dist_km = haversine_km(lon, lat, cc[0], cc[1])
    return dist_km > ADDRESS_NEIGHBORHOOD_AUTOLINK_MAX_KM


def _political_district_recall_identity_preflight(
    session: Session,
    *,
    location: SubstrateLocation,
    entry: dict[str, Any],
    recall: list[tuple[str, Any]],
) -> CanonicalPersistPlan | None:
    """Defer when PlaceExtract district identity does not match any recalled canonical."""
    if not strict_canonical_gates_enabled():
        return None
    lt = (location.location_type or "").strip().lower()
    if lt != "political_district":
        return None
    comps = place_extract_components_from_entry(location, entry)
    want = district_identity_key(district_identity_from_components(comps))
    if not want:
        return None
    ids = [str(cid) for cid, _ in recall[:48] if cid is not None and str(cid).strip()]
    if not ids:
        return None
    rows = session.exec(
        select(StylebookLocationCanonical).where(col(StylebookLocationCanonical.id).in_(ids))
    ).all()
    for c in rows:
        ck = (c.district_key or "").strip()
        if ck == want:
            return None
    return CanonicalPersistPlan(
        decision=CanonicalPersistDecision.DEFER,
        resolution_reasons=(
            {
                "code": "district_identity_mismatch",
                "message": (
                    "Political district identity from PlaceExtract does not match any "
                    "recalled canonical district key"
                ),
                "location_type": location.location_type,
                "details": {
                    "district_key": want,
                    "recall_canonical_ids": ids[:24],
                },
            },
        ),
    )


def _substrate_preflight_strict_gates(
    session: Session,
    *,
    location: SubstrateLocation,
    entry: dict[str, Any],
) -> CanonicalPersistPlan | None:
    """Gate D/E/F on the substrate row before alias / recall (returns DEFER plan or ``None``)."""
    if not strict_canonical_gates_enabled():
        return None
    comps = place_extract_components_from_entry(location, entry)
    mm = geocode_components_vs_formatted_address_mismatch(
        formatted_address=location.formatted_address,
        comps=comps,
    )
    if mm:
        msg = {
            "geocode_country_mismatch": "PlaceExtract country disagrees with geocoder address",
            "geocode_state_mismatch": "PlaceExtract state disagrees with geocoder address",
        }.get(mm, "Geocode vs components mismatch")
        return CanonicalPersistPlan(
            decision=CanonicalPersistDecision.DEFER,
            resolution_reasons=(
                {
                    "code": mm,
                    "message": msg,
                    "location_type": location.location_type,
                },
            ),
        )
    gj = location.geometry_json
    sub_centroid = geojson_bbox_centroid(gj) if isinstance(gj, dict) else None
    lt = (location.location_type or "").strip().lower()
    max_km: float | None = None
    if lt in ("place", "address"):
        max_km = 150.0
    elif lt == "neighborhood":
        max_km = 50.0
    elif lt == "region_city":
        max_km = 100.0
    if (
        max_km is not None
        and sub_centroid is not None
        and location.project_id is not None
    ):
        cq = container_admin_query_from_components(comps)
        if cq:
            ref_json = try_resolve_substrate_location_cache_geometry(
                session,
                project_id=int(location.project_id),
                location_text=cq,
            )
            ref_centroid = geojson_bbox_centroid(ref_json) if ref_json else None
            if ref_centroid is not None:
                dist = haversine_km(
                    sub_centroid[0],
                    sub_centroid[1],
                    ref_centroid[0],
                    ref_centroid[1],
                )
                if dist > max_km:
                    return CanonicalPersistPlan(
                        decision=CanonicalPersistDecision.DEFER,
                        resolution_reasons=(
                            {
                                "code": "geocode_distance_anomaly",
                                "message": (
                                    "Geocode centroid is unusually far from "
                                    "cached container city geocode"
                                ),
                                "location_type": location.location_type,
                                "details": {
                                    "container_query": cq,
                                    "distance_km": round(dist, 3),
                                    "max_km": max_km,
                                },
                            },
                        ),
                    )
    if isinstance(gj, dict):
        gtype = str(gj.get("type") or "").lower()
        if gtype in ("polygon", "multipolygon"):
            diag = geojson_bbox_diagonal_km(gj)
            max_diag: float | None = None
            if lt in ("place", "address"):
                max_diag = 5.0
            elif lt == "neighborhood":
                max_diag = 50.0
            else:
                max_diag = None
            if max_diag is not None and diag is not None and diag > max_diag:
                return CanonicalPersistPlan(
                    decision=CanonicalPersistDecision.DEFER,
                    resolution_reasons=(
                        {
                            "code": "geocode_bbox_scale_mismatch",
                            "message": (
                                "Geocode polygon span is implausibly large for this location type"
                            ),
                            "location_type": location.location_type,
                            "details": {
                                "diagonal_km": round(diag, 3),
                                "max_diagonal_km": max_diag,
                            },
                        },
                    ),
                )
    return None


def rank_scored_canonical_recall_matches(
    session: Session,
    *,
    location: SubstrateLocation,
    recall: list[tuple[str, float | None]],
    entry: dict[str, Any] | None = None,
) -> list[tuple[str, str, float, int]]:
    """Score each recalled canonical; return best-first rows.

    Each tuple is ``(canonical_id, label, score, recall_index)``. Tie-break on equal
    ``score``: higher ``recall_index`` wins, matching fuzzy ``best_id`` selection in
    :func:`decide_canonical_persist_plan`.
    """
    if not recall:
        return []
    cids = [cid for cid, _ in recall]
    bundles = load_canonical_match_features(session, canonical_ids=cids)
    comps = place_extract_components_from_entry(location, entry)
    substrate = SubstrateMatchInput(
        name=str(location.name),
        normalized_name=str(location.normalized_name),
        geometry_json=location.geometry_json,
        formatted_address=location.formatted_address,
    )
    rows: list[tuple[int, str, str, float]] = []
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
        if not types_are_comparable(location.location_type, canon.location_type):
            sc = min(sc, RECALL_MIN_SCORE - 0.001)
        if strict_canonical_gates_enabled() and _jurisdiction_pair_demotes_recall_score(
            location, canon, comps
        ):
            sc = min(sc, RECALL_MIN_SCORE - 0.001)
        if strict_canonical_gates_enabled() and _district_identity_pair_mismatch(comps, canon):
            sc = min(sc, RECALL_MIN_SCORE - 0.001)
        if strict_canonical_gates_enabled() and _address_neighborhood_geometry_demotes_recall(
            location, canon, feat
        ):
            sc = min(sc, RECALL_MIN_SCORE - 0.001)
        rows.append((recall_index, str(canon_id), str(canon.label), sc))
    rows.sort(key=lambda r: (-r[3], -r[0]))
    return [(r[1], r[2], r[3], r[0]) for r in rows]


def _best_allowed_recall_score(
    session: Session,
    *,
    substrate_location_type: str | None,
    ranked: list[tuple[str, str, float, int]],
) -> float | None:
    """Return best recall score among canonicals allowed to link (strict matrix).

    When we "compare broadly" for retrieval, cross-type candidates can land in the
    ambiguous band and block materializing a new canonical even when there is no
    *linkable* candidate. This helper lets policy treat "ambiguous but disallowed"
    as "no match" for materialization decisions.
    """
    if not ranked:
        return None
    s_lt = (substrate_location_type or "").strip().lower()
    if not s_lt:
        return max(sc for _cid, _lab, sc, _idx in ranked)
    ids = [cid for cid, _lab, _sc, _idx in ranked[:24]]
    rows = session.exec(
        select(StylebookLocationCanonical).where(col(StylebookLocationCanonical.id).in_(ids))
    ).all()
    lt_by_id: dict[str, str | None] = {}
    for c in rows:
        if c.id is not None:
            lt_by_id[str(c.id)] = c.location_type
    best: float | None = None
    for cid, _lab, sc, _idx in ranked:
        c_lt = lt_by_id.get(str(cid))
        if link_pair_allowed(s_lt, c_lt) and not autolink_container_to_fine_denied(s_lt, c_lt):
            best = sc if best is None else max(best, sc)
    return best


def _should_materialize_when_no_canonical_match(location: SubstrateLocation) -> bool:
    """After exact match + fuzzy tiers: whether to create a new canonical.

    Most location types get a canonical when nothing linked and recall is not ambiguous,
    as long as the row is not a hard geocode failure and has a normalized name.

    Address, intersections, and span / street-road types keep the strict geometry rule.
    Spans never materialize automatically (always defer).
    """
    lt = (location.location_type or "").strip().lower()
    if lt == "span":
        return False
    if _location_type_allows_autocreate_without_strict_geometry(location.location_type):
        st = str(location.status or "")
        if st == "failed":
            return False
        if not str(location.normalized_name or "").strip():
            return False
        return True
    return _should_materialize_new_strict(location)


def _intra_strict_group_ambiguous(
    session: Session,
    location: SubstrateLocation,
    ranked: list[tuple[str, str, float, int]],
) -> bool:
    """True when two or more candidates share the substrate's strict type group at autolink tier."""
    sg = strict_type_group(location.location_type)
    if sg is None:
        return False
    n = 0
    for cid, _lab, sc, _idx in ranked:
        if sc < AUTOLINK_MIN_SCORE:
            break
        canon = session.get(StylebookLocationCanonical, cid)
        if canon is None:
            continue
        if not link_pair_allowed(location.location_type, canon.location_type):
            continue
        if autolink_container_to_fine_denied(location.location_type, canon.location_type):
            continue
        if strict_type_group(canon.location_type) != sg:
            continue
        n += 1
        if n >= 2:
            return True
    return False


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
        if lt == "span":
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.DEFER,
                resolution_reasons=(
                    {
                        "code": "road_span_not_canonicalized",
                        "message": (
                            "Road spans are not auto-canonicalized; "
                            "defer for manual review or linking."
                        ),
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

    preflight = _substrate_preflight_strict_gates(session, location=location, entry=entry)
    if preflight is not None:
        return preflight

    cid = find_existing_canonical_id_by_alias(
        session, stylebook_id=stylebook_id, normalized_name=str(location.normalized_name)
    )
    if cid is not None:
        alias_canon = session.get(StylebookLocationCanonical, cid)
        alias_canon_lt = alias_canon.location_type if alias_canon is not None else None
        alias_pair_ok = link_pair_allowed(location.location_type, alias_canon_lt) and not (
            autolink_container_to_fine_denied(location.location_type, alias_canon_lt)
        )
        if alias_pair_ok:
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.LINK_EXISTING,
                existing_canonical_id=cid,
                resolution_reasons=(
                    {
                        "code": "linked_exact_normalized_alias",
                        "canonical_id": str(cid),
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
        substrate_location_type=location.location_type,
    )
    best_id: str | None = None
    best_score = 0.0
    recall_canonical_ids: tuple[str, ...] = ()
    intra_ambiguous = False
    if recall:
        recall_canonical_ids = tuple(str(cid) for cid, _ in recall)
        pd_pf = _political_district_recall_identity_preflight(
            session, location=location, entry=entry, recall=list(recall)
        )
        if pd_pf is not None:
            return pd_pf
        ranked = rank_scored_canonical_recall_matches(
            session, location=location, recall=list(recall), entry=entry
        )
        if ranked:
            best_id, best_score = ranked[0][0], ranked[0][2]
        tier = classify_recall_score(best_score)
        intra_ambiguous = (
            tier == "autolink"
            and best_id is not None
            and _intra_strict_group_ambiguous(session, location, ranked)
        )
        if intra_ambiguous:
            tier = "ambiguous"
        if tier == "autolink" and best_id is not None:
            best_canon = session.get(StylebookLocationCanonical, str(best_id))
            best_lt = best_canon.location_type if best_canon is not None else None
            best_pair_bad = not link_pair_allowed(
                location.location_type, best_lt
            ) or autolink_container_to_fine_denied(location.location_type, best_lt)
            if best_pair_bad:
                tier = "ambiguous"
                intra_ambiguous = True
        if tier == "autolink" and best_id is not None:
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.LINK_EXISTING,
                existing_canonical_id=str(best_id),
                resolution_reasons=(
                    {
                        "code": "linked_fuzzy_autolink",
                        "canonical_id": str(best_id),
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
            # If recall is only "ambiguous" because of cross-type candidates we would never
            # auto-link, treat it as "no match" so the substrate may materialize its own canonical.
            if _should_materialize_when_no_canonical_match(location):
                best_allowed = _best_allowed_recall_score(
                    session,
                    substrate_location_type=location.location_type,
                    ranked=ranked,
                )
                if best_allowed is None or best_allowed < RECALL_MIN_SCORE:
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
                                "fuzzy_best_score_before_materialize": float(best_score),
                                "fuzzy_recall_canonical_ids": list(recall_canonical_ids[:24]),
                                "fuzzy_best_link_allowed_score": float(best_allowed)
                                if best_allowed is not None
                                else None,
                            },
                        ),
                    )
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.DEFER,
                resolution_reasons=(
                    {
                        "code": "ambiguous_canonical_match",
                        "best_canonical_id": str(best_id),
                        "best_score": float(best_score),
                        "autolink_min_score": float(AUTOLINK_MIN_SCORE),
                        "recall_min_score": float(RECALL_MIN_SCORE),
                        "match_basis": _match_basis_for_audit(location.location_type),
                        "head_anchor_gate_applied": _should_apply_head_anchor_gate(
                            location.location_type
                        ),
                        "type_gate_applied": True,
                        "intra_strict_group_ambiguous": intra_ambiguous,
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


def plan_requires_llm_canonical_adjudication(
    plan: CanonicalPersistPlan,
    location: SubstrateLocation,
) -> bool:
    """True when AI-assisted mode should run LLM adjudication."""
    if plan_has_ambiguous_canonical_match(plan):
        return True
    lt = (location.location_type or "").strip().lower()
    if lt != "political_district":
        return False
    if plan.decision != CanonicalPersistDecision.LINK_EXISTING:
        return False
    for r in plan.resolution_reasons:
        if isinstance(r, dict) and str(r.get("code") or "") == "linked_fuzzy_autolink":
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
