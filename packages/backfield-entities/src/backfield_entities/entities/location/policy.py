"""Location canonical persist policy: when to link, materialize, or defer."""

from __future__ import annotations

from typing import Any

from backfield_db import StylebookLocationCanonical, SubstrateLocation
from sqlmodel import Session, col, select

from backfield_entities.canonical.jurisdiction import (
    container_admin_query_from_components,
    district_identity_from_components,
    district_identity_key,
    district_kind_keywords_conflict,
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
from backfield_entities.canonical.link_commit_gate import (
    gate_or_coerce_link_plan,
    sync_link_commit_blocked,
)
from backfield_entities.canonical.link_matrix import (
    autolink_container_to_fine_denied,
    link_pair_allowed,
    strict_type_group,
    types_are_comparable,
)
from backfield_entities.canonical.match_score import (
    AUTOLINK_MIN_SCORE,
    RECALL_MIN_SCORE,
    CanonicalMatchFeatures,
    SubstrateMatchInput,
    _loose_key,
    classify_recall_score,
    policy_match_score,
)
from backfield_entities.canonical.plan_types import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)
from backfield_entities.canonical.retrieval import (
    load_canonical_match_features,
    retrieve_candidate_canonical_ids,
)
from backfield_entities.entities.location.recall import (
    canonical_ids_from_location_name_keys,
)
from backfield_entities.entities.location.review_display import deferred_policy_display_message
from backfield_entities.entities.location.types import (
    ADDRESS_PLACE_KIND_PRIVATE_RESIDENCE,
    ADDRESS_PLACE_KIND_PUBLIC_NAMED,
    ADDRESS_PLACE_KIND_UNKNOWN,
    is_address_like_location_type,
)
from backfield_entities.ingest.geocode_cache.fingerprint import normalize_substrate_cache_query
from backfield_entities.ingest.geocode_cache.resolve import (
    try_resolve_substrate_location_cache_geometry,
)
from backfield_entities.ingest.geocode_cache.sanity import (
    substrate_canonical_link_blocked_by_content_sanity,
)
from backfield_entities.text.match_normalize import match_fold_key

# Scores at or below this value are treated as gate-demoted (just under recall floor).
_RECALL_SCORE_DEMOTED: float = RECALL_MIN_SCORE - 0.001


def find_existing_canonical_id_by_alias(
    session: Session,
    *,
    stylebook_id: int,
    normalized_name: str,
) -> str | None:
    """Return ``StylebookLocationCanonical.id`` if an alias matches in this Stylebook."""
    ids = canonical_ids_from_location_name_keys(
        session,
        stylebook_id=stylebook_id,
        name_or_norm=str(normalized_name),
        trusted_alias_only=True,
    )
    if not ids:
        return None
    return ids[0]


def find_existing_canonical_id_by_normalized_label(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
) -> str | None:
    """Return canonical id when exactly one active row matches geocode tier-1 label rules."""
    winners = canonical_ids_by_normalized_label(
        session,
        stylebook_id=stylebook_id,
        location=location,
    )
    if len(winners) != 1:
        return None
    return winners[0]


def canonical_ids_by_normalized_label(
    session: Session,
    *,
    stylebook_id: int,
    location: SubstrateLocation,
) -> list[str]:
    """Return every active canonical whose label exactly matches the substrate keys."""
    queries: set[str] = set()
    for raw in (location.name, location.normalized_name):
        n = normalize_substrate_cache_query(str(raw or ""))
        if n:
            queries.add(n)
        folded = match_fold_key(str(raw or ""))
        if folded:
            queries.add(folded)
    if not queries:
        return []
    canons = session.exec(
        select(StylebookLocationCanonical).where(
            StylebookLocationCanonical.stylebook_id == stylebook_id,
            StylebookLocationCanonical.status == "active",
        )
    ).all()
    winners: list[str] = []
    for canon in canons:
        if canon.id is None:
            continue
        label_keys = {
            normalize_substrate_cache_query(str(canon.label)),
            match_fold_key(str(canon.label)),
        }
        if label_keys & queries:
            winners.append(str(canon.id))
    return sorted(set(winners))


def _surviving_exact_location_candidate_ids(
    session: Session,
    *,
    candidate_ids: list[str],
    stylebook_id: int,
    location: SubstrateLocation,
    entry: dict[str, Any],
) -> list[str]:
    """Apply the final commit invariant to an unordered exact candidate set."""
    survivors: list[str] = []
    for canonical_id in sorted(set(candidate_ids)):
        veto = sync_link_commit_blocked(
            session,
            entity_type="location",
            substrate_row=location,
            canonical_id=canonical_id,
            stylebook_id=stylebook_id,
            entry=entry,
        )
        if veto is None:
            survivors.append(canonical_id)
    return survivors


def _ambiguous_exact_location_plan(candidate_ids: list[str]) -> CanonicalPersistPlan:
    return CanonicalPersistPlan(
        decision=CanonicalPersistDecision.DEFER,
        resolution_reasons=(
            {
                "code": "ambiguous_exact_canonical_match",
                "recall_canonical_ids": sorted(set(candidate_ids))[:24],
                "match_basis": "exact_alias_candidate_set",
            },
        ),
    )


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


def _address_place_kind(
    location: SubstrateLocation,
    entry: dict[str, Any] | None,
) -> str:
    kind = _address_place_kind_from_entry(entry)
    if kind != ADDRESS_PLACE_KIND_UNKNOWN:
        return kind
    details = location.source_details_json
    if isinstance(details, dict):
        return _address_place_kind_from_entry(details)
    return ADDRESS_PLACE_KIND_UNKNOWN


def _is_private_place_or_residence(
    location: SubstrateLocation,
    entry: dict[str, Any] | None,
) -> bool:
    lt = (location.location_type or "").strip().lower()
    return (
        is_address_like_location_type(lt)
        and _address_place_kind(location, entry) == ADDRESS_PLACE_KIND_PRIVATE_RESIDENCE
    )


_NO_AUTOMATIC_CANONICAL_MATERIALIZATION_TYPES: frozenset[str] = frozenset(
    {
        "address",
        "intersection_highway",
        "intersection_road",
        "street_road",
    }
)

# Types that never auto-materialize a canonical, even with resolved geocode + geometry.
# Editors can still link these to existing canonicals or create canonicals manually.
_NEVER_AUTO_MATERIALIZE_TYPES: frozenset[str] = frozenset(
    {
        "span",
        "intersection_road",
        "intersection_highway",
    }
)

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


_COMPASS_AXIS_EAST: frozenset[str] = frozenset({"east", "eastern"})
_COMPASS_AXIS_WEST: frozenset[str] = frozenset({"west", "western"})
_COMPASS_AXIS_NORTH: frozenset[str] = frozenset({"north", "northern"})
_COMPASS_AXIS_SOUTH: frozenset[str] = frozenset({"south", "southern"})
_COMPOUND_COMPASS_AXES: dict[str, frozenset[str]] = {
    "northeast": frozenset({"north", "east"}),
    "northeastern": frozenset({"north", "east"}),
    "northwest": frozenset({"north", "west"}),
    "northwestern": frozenset({"north", "west"}),
    "southeast": frozenset({"south", "east"}),
    "southeastern": frozenset({"south", "east"}),
    "southwest": frozenset({"south", "west"}),
    "southwestern": frozenset({"south", "west"}),
}


def _compass_axes_from_head(display_name: str) -> frozenset[str]:
    """Compass axes named on the comma head (e.g. ``East Coast, US`` → ``{east}``)."""
    head = display_name.split(",")[0]
    loose = _loose_key(head)
    if not loose:
        return frozenset()
    axes: set[str] = set()
    for token in loose.split():
        compound = _COMPOUND_COMPASS_AXES.get(token)
        if compound is not None:
            axes.update(compound)
            continue
        if token in _COMPASS_AXIS_EAST:
            axes.add("east")
        if token in _COMPASS_AXIS_WEST:
            axes.add("west")
        if token in _COMPASS_AXIS_NORTH:
            axes.add("north")
        if token in _COMPASS_AXIS_SOUTH:
            axes.add("south")
    return frozenset(axes)


def _compass_axes_conflict(left: frozenset[str], right: frozenset[str]) -> bool:
    if not left or not right:
        return False
    if "east" in left and "west" in right:
        return True
    if "west" in left and "east" in right:
        return True
    if "north" in left and "south" in right:
        return True
    if "south" in left and "north" in right:
        return True
    return False


def _compass_direction_conflict(substrate_name: str, candidate: CanonicalMatchFeatures) -> bool:
    """True when substrate and candidate name heads name opposing compass directions."""
    sub_axes = _compass_axes_from_head(substrate_name)
    if not sub_axes:
        return False
    for surface in (str(candidate.label), *candidate.normalized_aliases):
        if _compass_axes_conflict(sub_axes, _compass_axes_from_head(str(surface))):
            return True
    return False


def _match_basis_for_audit(location_type: str | None) -> str:
    if (location_type or "").strip().lower() == "address":
        return "string_and_point_geometry"
    return "string_only"


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
    c_country = (canon.country_code or "").strip().upper()[:2] or None
    c_sub = (canon.subdivision_code or "").strip().upper()[:2] or None
    c_lt = (canon.location_type or "").strip().lower()
    if c_lt in _POI_LIKE_CANON_TYPES and not (c_country and c_sub):
        return False
    if c_country and s_country and s_country != c_country:
        return True
    if c_sub and s_sub and s_sub != c_sub:
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


def _district_kind_keyword_pair_mismatch(
    location: SubstrateLocation,
    canon: StylebookLocationCanonical,
) -> bool:
    """True when district-kind keywords disagree for a political-district pairing.

    Catches rows without a structured district identity (e.g. a judicial "subcircuit"
    phrase misfiled in the city component) that would otherwise fuzzy-match a
    same-numbered congressional district, ward, or state legislative district.
    """
    s_lt = (location.location_type or "").strip().lower()
    c_lt = (canon.location_type or "").strip().lower()
    if s_lt != "political_district" and c_lt != "political_district":
        return False
    return district_kind_keywords_conflict(
        (str(location.name or ""), str(location.formatted_address or "")),
        (str(canon.label or ""), str(canon.formatted_address or "")),
    )


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
            "geocode_country_mismatch": (
                "Place extraction disagrees with the geocoded address on country — "
                "confirm before linking"
            ),
            "geocode_state_mismatch": (
                "Place extraction disagrees with the geocoded address on state or province — "
                "confirm before linking"
            ),
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


def _apply_recall_match_gates(
    raw_score: float,
    *,
    location: SubstrateLocation,
    canon: StylebookLocationCanonical,
    feat: CanonicalMatchFeatures,
    comps: dict[str, Any],
) -> float:
    """Apply deterministic recall gates; return gated score (may clamp below recall floor)."""
    sc = float(raw_score)
    gate_lt = _should_apply_head_anchor_gate(location.location_type)
    if gate_lt and not _head_anchor_gate_passes(str(location.name), feat):
        sc = min(sc, _RECALL_SCORE_DEMOTED)
    if _compass_direction_conflict(str(location.name), feat):
        sc = min(sc, _RECALL_SCORE_DEMOTED)
    if not types_are_comparable(location.location_type, canon.location_type):
        sc = min(sc, _RECALL_SCORE_DEMOTED)
    if strict_canonical_gates_enabled() and _jurisdiction_pair_demotes_recall_score(
        location, canon, comps
    ):
        sc = min(sc, _RECALL_SCORE_DEMOTED)
    if strict_canonical_gates_enabled() and _district_identity_pair_mismatch(comps, canon):
        sc = min(sc, _RECALL_SCORE_DEMOTED)
    if strict_canonical_gates_enabled() and _district_kind_keyword_pair_mismatch(location, canon):
        sc = min(sc, _RECALL_SCORE_DEMOTED)
    if strict_canonical_gates_enabled() and _address_neighborhood_geometry_demotes_recall(
        location, canon, feat
    ):
        sc = min(sc, _RECALL_SCORE_DEMOTED)
    if strict_canonical_gates_enabled() and substrate_canonical_link_blocked_by_content_sanity(
        substrate_location_type=location.location_type,
        location_text=str(location.name),
        components=comps,
        match_label=str(canon.label),
        match_formatted_address=canon.formatted_address,
        match_location_type=canon.location_type,
        match_geometry_type=canon.geometry_type,
    ):
        sc = min(sc, _RECALL_SCORE_DEMOTED)
    return sc


def recall_match_gate_demoted_below_threshold(raw_score: float, gated_score: float) -> bool:
    """True when gates dropped an otherwise-recallable match below the recall floor."""
    if raw_score < RECALL_MIN_SCORE:
        return False
    if gated_score >= RECALL_MIN_SCORE:
        return False
    return gated_score <= _RECALL_SCORE_DEMOTED + 1e-9


def rank_scored_canonical_recall_matches(
    session: Session,
    *,
    location: SubstrateLocation,
    recall: list[tuple[str, float | None]],
    entry: dict[str, Any] | None = None,
) -> list[tuple[str, str, float, int, float]]:
    """Score each recalled canonical; return best-first rows.

    Each tuple is ``(canonical_id, label, gated_score, recall_index, raw_score)``.
    Tie-break on equal ``gated_score``: higher ``recall_index`` wins, matching fuzzy
    ``best_id`` selection in :func:`decide_location_canonical_persist_plan`.
    """
    if not recall:
        return []
    cids = [cid for cid, _ in recall]
    bundles = load_canonical_match_features(
        session, canonical_ids=cids, trusted_alias_only=True
    )
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
        raw_sc = float(
            policy_match_score(
                substrate,
                feat,
                substrate_location_type=location.location_type,
            )
        )
        sc = _apply_recall_match_gates(
            raw_sc,
            location=location,
            canon=canon,
            feat=feat,
            comps=comps,
        )
        rows.append((recall_index, str(canon_id), str(canon.label), sc, raw_sc))
    rows.sort(key=lambda r: (-r[3], -r[0]))
    return [(r[1], r[2], r[3], r[0], r[4]) for r in rows]


def _best_allowed_recall_score(
    session: Session,
    *,
    substrate_location_type: str | None,
    ranked: list[tuple[str, str, float, int, float]],
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
        return max(sc for _cid, _lab, sc, _idx, _raw in ranked)
    ids = [cid for cid, _lab, _sc, _idx, _raw in ranked[:24]]
    rows = session.exec(
        select(StylebookLocationCanonical).where(col(StylebookLocationCanonical.id).in_(ids))
    ).all()
    lt_by_id: dict[str, str | None] = {}
    for c in rows:
        if c.id is not None:
            lt_by_id[str(c.id)] = c.location_type
    best: float | None = None
    for cid, _lab, sc, _idx, _raw in ranked:
        c_lt = lt_by_id.get(str(cid))
        if link_pair_allowed(s_lt, c_lt) and not autolink_container_to_fine_denied(s_lt, c_lt):
            best = sc if best is None else max(best, sc)
    return best


def _should_materialize_when_no_canonical_match(location: SubstrateLocation) -> bool:
    """After exact match + fuzzy tiers: whether to recommend a new canonical.

    Missing or rejected geography is not evidence against the extracted identity. Most
    named location types may therefore recommend a geography-free canonical. Persistence
    separately prevents review-required geography from auto-materializing.
    """
    lt = (location.location_type or "").strip().lower()
    if lt in _NEVER_AUTO_MATERIALIZE_TYPES:
        return False
    return bool(str(location.normalized_name or "").strip())


def _intra_strict_group_ambiguous(
    session: Session,
    location: SubstrateLocation,
    ranked: list[tuple[str, str, float, int, float]],
) -> bool:
    """True when two or more candidates share the substrate's strict type group at autolink tier."""
    sg = strict_type_group(location.location_type)
    if sg is None:
        return False
    n = 0
    for cid, _lab, sc, _idx, _raw in ranked:
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


def _decide_location_identity_plan(
    session: Session,
    *,
    stylebook_id: int,
    places_bucket: str,
    location: SubstrateLocation,
    entry: dict[str, Any],
) -> CanonicalPersistPlan:
    """Decide canonical identity without treating missing geography as a conflict.

    ``entry`` carries PlaceExtract extras (e.g. ``address_place_kind``) for address deferral rules.
    """
    if _is_private_place_or_residence(location, entry):
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
    if (location.location_type or "").strip().lower() == "span":
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

    preflight = _substrate_preflight_strict_gates(session, location=location, entry=entry)
    if preflight is not None:
        return preflight

    alias_candidate_ids = canonical_ids_from_location_name_keys(
        session,
        stylebook_id=stylebook_id,
        name_or_norm=str(location.normalized_name),
        trusted_alias_only=True,
    )
    exact_link_code = "linked_exact_normalized_alias"
    exact_match_basis = "exact_alias_lookup"
    exact_candidate_ids = alias_candidate_ids
    survivors = _surviving_exact_location_candidate_ids(
        session,
        candidate_ids=exact_candidate_ids,
        stylebook_id=stylebook_id,
        location=location,
        entry=entry,
    )
    if not survivors:
        exact_candidate_ids = canonical_ids_by_normalized_label(
            session,
            stylebook_id=stylebook_id,
            location=location,
        )
        survivors = _surviving_exact_location_candidate_ids(
            session,
            candidate_ids=exact_candidate_ids,
            stylebook_id=stylebook_id,
            location=location,
            entry=entry,
        )
        if survivors:
            exact_link_code = "linked_exact_normalized_label"
            exact_match_basis = "exact_normalized_label"
    if len(survivors) > 1:
        return _ambiguous_exact_location_plan(survivors)
    if len(survivors) == 1:
        cid = survivors[0]
        return gate_or_coerce_link_plan(
            session,
            CanonicalPersistPlan(
                decision=CanonicalPersistDecision.LINK_EXISTING,
                existing_canonical_id=cid,
                resolution_reasons=(
                    {
                        "code": exact_link_code,
                        "canonical_id": str(cid),
                        "normalized_name": str(location.normalized_name),
                        "match_basis": exact_match_basis,
                        "type_gate_applied": True,
                        "exact_candidate_ids": sorted(set(exact_candidate_ids))[:24],
                    },
                ),
            ),
            entity_type="location",
            substrate_row=location,
            stylebook_id=stylebook_id,
            entry=entry,
        )

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
    best_raw_score = 0.0
    recall_canonical_ids: tuple[str, ...] = ()
    intra_ambiguous = False
    ranked: list[tuple[str, str, float, int, float]] = []
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
            best_id, best_score, best_raw_score = ranked[0][0], ranked[0][2], ranked[0][4]
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
            return gate_or_coerce_link_plan(
                session,
                CanonicalPersistPlan(
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
                ),
                entity_type="location",
                substrate_row=location,
                stylebook_id=stylebook_id,
                entry=entry,
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
        if (
            ranked
            and best_id is not None
            and classify_recall_score(best_score) == "below_recall"
            and recall_match_gate_demoted_below_threshold(best_raw_score, best_score)
        ):
            return CanonicalPersistPlan(
                decision=CanonicalPersistDecision.DEFER,
                resolution_reasons=(
                    {
                        "code": "ambiguous_canonical_match",
                        "best_canonical_id": str(best_id),
                        "best_score": float(best_score),
                        "fuzzy_raw_score_before_gates": float(best_raw_score),
                        "gate_demoted_recall_match": True,
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
            entry=entry,
            extra_context={
                "fuzzy_best_score": float(best_score) if recall_canonical_ids else None,
                "fuzzy_recall_canonical_ids": list(recall_canonical_ids[:24])
                if recall_canonical_ids
                else None,
            },
        ),
    )


def _geocode_quality_warning_payload(
    *,
    places_bucket: str,
    location: SubstrateLocation,
    entry: dict[str, Any] | None,
) -> tuple[dict[str, Any], ...]:
    status = str(location.status or "").strip().lower()
    if places_bucket != "needs_review" and status not in {"needs_review", "failed"}:
        return ()
    warning = dict(
        defer_reason_payload(
            places_bucket=places_bucket,
            location=location,
            entry=entry,
        )[0]
    )
    warning["code"] = "geocode_quality_warning"
    return (warning,)


def decide_location_canonical_persist_plan(
    session: Session,
    *,
    stylebook_id: int,
    places_bucket: str,
    location: SubstrateLocation,
    entry: dict[str, Any],
) -> CanonicalPersistPlan:
    """Decide identity, preserving geocode concerns as non-blocking review warnings."""
    plan = _decide_location_identity_plan(
        session,
        stylebook_id=stylebook_id,
        places_bucket=places_bucket,
        location=location,
        entry=entry,
    )
    warnings = _geocode_quality_warning_payload(
        places_bucket=places_bucket,
        location=location,
        entry=entry,
    )
    if not warnings:
        return plan
    return CanonicalPersistPlan(
        decision=plan.decision,
        existing_canonical_id=plan.existing_canonical_id,
        resolution_reasons=warnings + plan.resolution_reasons,
    )


def plan_has_ambiguous_canonical_match(plan: CanonicalPersistPlan) -> bool:
    """True when rules deferred with an ambiguous fuzzy recall (LLM adjudication hook)."""
    for r in plan.resolution_reasons:
        if isinstance(r, dict) and str(r.get("code") or "") in {
            "ambiguous_canonical_match",
            "ambiguous_exact_canonical_match",
        }:
            return True
    return False


def plan_requires_llm_canonical_adjudication(
    plan: CanonicalPersistPlan,
    location: SubstrateLocation,
) -> bool:
    """True when AI-assisted mode should run LLM adjudication."""
    if plan_has_ambiguous_canonical_match(plan):
        return True
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
    entry: dict[str, Any] | None = None,
    extra_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Structured reasons for ``canonical_review_reasons_json`` when deferring."""
    d: dict[str, Any] = {
        "code": "deferred_policy",
        "places_bucket": places_bucket,
        "substrate_status": str(location.status or ""),
        "location_type": location.location_type,
    }
    if isinstance(entry, dict):
        qa = entry.get("geocode_qa_code")
        if isinstance(qa, str) and qa.strip():
            d["geocode_qa_code"] = qa.strip()
    if extra_context:
        for k, v in extra_context.items():
            if v is not None:
                d[k] = v
    d["message"] = deferred_policy_display_message(d)
    return (d,)
