"""Merge immutable model ``locations`` with review overlay for processed items.

See ``docs/API.md`` → *Processed item location overlay (v1)* for the JSON contract.
"""

from __future__ import annotations

import copy
from typing import Any

from api.processed_item_mention_occurrences import (
    build_mention_occurrences_for_row,
    sync_original_text_from_occurrences,
)

BaselineRow = tuple[str, str, int, dict[str, Any]]

# When multiple pipeline nodes emit ``places``, use one canonical bucket for review.
_GEOCODED_PLACES_NODE_PRIORITY: tuple[str, ...] = (
    "stylebook_output",
    "stylebook-output",
    "DBOutput",
    "db_output",
    "GeocodeAgent",
    "geocode_agent",
    "Geocode",
)

# PlaceExtract output is never a review or persistence baseline (geocode / DBOutput only).
_PLACE_EXTRACT_NODE_IDS: frozenset[str] = frozenset(
    {"place_extract", "PlaceExtract"},
)


def _node_ids_with_places(output: dict[str, Any] | None) -> frozenset[str]:
    """Node output keys whose payload includes a GeocodeAgent ``places`` bucket."""
    ids: set[str] = set()
    if not output or not isinstance(output, dict):
        return frozenset()
    for node_id, payload in output.items():
        if isinstance(payload, dict) and isinstance(payload.get("places"), dict):
            ids.add(str(node_id))
    return frozenset(ids)


def _geocoded_places_node_candidates(output: dict[str, Any] | None) -> frozenset[str]:
    """Node keys with ``places`` that may feed review (excludes PlaceExtract)."""
    excluded_lower = {n.lower() for n in _PLACE_EXTRACT_NODE_IDS}
    return frozenset(
        n
        for n in _node_ids_with_places(output)
        if n not in _PLACE_EXTRACT_NODE_IDS and n.lower() not in excluded_lower
    )


def _select_geocoded_places_node_id(output: dict[str, Any] | None) -> str | None:
    """Pick one node output for geocoded ``places`` when several carry the same bucket."""
    places_nodes = _geocoded_places_node_candidates(output)
    if not places_nodes:
        return None
    node_set = {str(n) for n in places_nodes}
    for pref in _GEOCODED_PLACES_NODE_PRIORITY:
        if pref in node_set:
            return pref
    lower_map = {n.lower(): n for n in node_set}
    for pref in _GEOCODED_PLACES_NODE_PRIORITY:
        hit = lower_map.get(pref.lower())
        if hit:
            return hit
    return sorted(node_set)[0]


def _shallow_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        out[k] = copy.deepcopy(v)
    return out


def _anchor_for_place_dict(loc: dict[str, Any], node_id: str, index: int) -> str:
    """Review overlay anchor: stable ``id`` / ``mention_id``, never a shared H3 cell alone.

    GeocodeAgent sets point ``id`` to ``h3:<cell>`` for colocation at one address. Multiple
    distinct extractions at the same coordinates must not collapse in ``merged_locations``.
    """
    for key in ("id", "mention_id"):
        raw = loc.get(key)
        if raw is None:
            continue
        s = str(raw).strip()
        if not s or s.startswith("h3:"):
            continue
        return s
    return f"{node_id}:{index}"


def _iter_rows_from_places_node(
    output: dict[str, Any],
    node_id: str,
) -> list[BaselineRow]:
    """``places`` rows for a single node output key."""
    rows: list[BaselineRow] = []
    payload = output.get(node_id)
    if not isinstance(payload, dict):
        return rows
    places = payload.get("places")
    if not isinstance(places, dict):
        return rows
    idx = 0
    areas = places.get("areas")
    if isinstance(areas, dict):
        for bucket in ("states", "counties", "cities", "neighborhoods", "regions", "other"):
            items = areas.get(bucket)
            if not isinstance(items, list):
                continue
            for loc in items:
                if not isinstance(loc, dict):
                    continue
                anchor = _anchor_for_place_dict(loc, node_id, idx)
                rows.append((anchor, node_id, idx, loc))
                idx += 1
    for bucket in ("points", "needs_review", "other"):
        items = places.get(bucket)
        if not isinstance(items, list):
            continue
        for loc in items:
            if not isinstance(loc, dict):
                continue
            anchor = _anchor_for_place_dict(loc, node_id, idx)
            rows.append((anchor, node_id, idx, loc))
            idx += 1
    return rows


def _iter_rows_from_places(output: dict[str, Any] | None) -> list[BaselineRow]:
    """``places`` rows from the canonical geocoded node only (if any)."""
    if not output or not isinstance(output, dict):
        return []
    node_id = _select_geocoded_places_node_id(output)
    if not node_id:
        return []
    return _iter_rows_from_places_node(output, node_id)


def _merge_baseline_place_rows(output: dict[str, Any] | None) -> list[BaselineRow]:
    """Build review baseline from geocoded ``places`` only (points, areas, needs_review).

    PlaceExtract ``locations`` are never merged into review. When no geocoded node has
    ``places``, the baseline is empty (user-added overlay rows may still appear).
    """
    geocoded_node = _select_geocoded_places_node_id(output)
    if not geocoded_node:
        return []
    merged_by_anchor: dict[str, BaselineRow] = {}
    order: list[str] = []
    for row in _iter_rows_from_places_node(output, geocoded_node):
        anchor = row[0]
        if anchor not in merged_by_anchor:
            order.append(anchor)
        merged_by_anchor[anchor] = row
    return [merged_by_anchor[a] for a in order]


def _normalize_locations_overlay(
    overlay: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return ``(by_anchor_patches, user_added_rows, removed_anchors)`` from overlay v1."""
    if not overlay or not isinstance(overlay, dict):
        return {}, [], set()
    loc_root = overlay.get("locations")
    if not isinstance(loc_root, dict):
        return {}, [], set()
    patches_raw = loc_root.get("by_anchor")
    patches: dict[str, Any] = {}
    if isinstance(patches_raw, dict):
        for k, v in patches_raw.items():
            if isinstance(k, str) and isinstance(v, dict):
                patches[k] = v
    user_added: list[dict[str, Any]] = []
    ua_raw = loc_root.get("user_added")
    if isinstance(ua_raw, list):
        for row in ua_raw:
            if isinstance(row, dict):
                user_added.append(row)
    removed: set[str] = set()
    removed_raw = loc_root.get("removed_anchors")
    if isinstance(removed_raw, list):
        for anchor in removed_raw:
            if isinstance(anchor, str) and anchor.strip():
                removed.add(anchor.strip())
    return patches, user_added, removed


def build_merged_locations_lane(
    *,
    output: dict[str, Any] | None,
    overlay: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build merged location lane + stale overlay anchors.

    Returns ``(merged_locations, stale_overlay_entries)``.
    """
    baseline = _merge_baseline_place_rows(output)
    patches, user_added, removed_anchors = _normalize_locations_overlay(overlay)

    merged: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []

    anchors_in_model = {a for a, _nid, _i, _loc in baseline}

    for anchor, node_id, idx, loc in baseline:
        if anchor in removed_anchors:
            continue
        loc_out = copy.deepcopy(loc)
        patch = patches.get(anchor)
        patch_dict = patch if isinstance(patch, dict) else None
        if patch_dict:
            loc_out = _shallow_merge_dict(loc_out, patch_dict)
        mention_occurrences = build_mention_occurrences_for_row(
            place=loc_out,
            overlay_patch=patch_dict,
            db_rows=None,
        )
        sync_original_text_from_occurrences(loc_out, mention_occurrences)
        merged.append(
            {
                "anchor": anchor,
                "source": "model",
                "node_id": node_id,
                "index_in_node": idx,
                "stale": False,
                "location": loc_out,
                "mention_occurrences": mention_occurrences,
            }
        )

    for anchor, patch in patches.items():
        if anchor not in anchors_in_model:
            stale.append(
                {
                    "anchor": anchor,
                    "reason": "anchor_missing_from_model_output",
                    "patch": copy.deepcopy(patch) if isinstance(patch, dict) else None,
                }
            )

    for row in user_added:
        rid = row.get("id")
        if not isinstance(rid, str) or not rid.startswith("user_place:"):
            continue
        loc_payload = row.get("location")
        if isinstance(loc_payload, dict):
            loc_out = copy.deepcopy(loc_payload)
        else:
            rest = {k: v for k, v in row.items() if k not in ("id", "location")}
            loc_out = rest if rest else {}
        mention_occurrences = build_mention_occurrences_for_row(
            place=loc_out,
            overlay_patch=None,
            db_rows=None,
        )
        sync_original_text_from_occurrences(loc_out, mention_occurrences)
        merged.append(
            {
                "anchor": rid,
                "source": "user",
                "node_id": None,
                "index_in_node": None,
                "stale": False,
                "location": loc_out,
                "mention_occurrences": mention_occurrences,
            }
        )

    return merged, stale
