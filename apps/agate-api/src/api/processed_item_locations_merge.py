"""Merge immutable model ``locations`` with review overlay for processed items.

See ``docs/API.md`` → *Processed item location overlay (v1)* for the JSON contract.
"""

from __future__ import annotations

import copy
from typing import Any

BaselineRow = tuple[str, str, int, dict[str, Any]]


def _shallow_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        out[k] = copy.deepcopy(v)
    return out


def _anchor_for_place_dict(loc: dict[str, Any], node_id: str, index: int) -> str:
    """Match review anchor rules: ``id``, else ``mention_id``, else ``{node_id}:{index}``."""
    aid = loc.get("id")
    if aid is None or aid == "":
        aid = loc.get("mention_id")
    if aid is None or aid == "":
        return f"{node_id}:{index}"
    return str(aid)


def _iter_rows_from_locations(output: dict[str, Any] | None) -> list[BaselineRow]:
    """``(anchor, node_id, index, place_dict)`` from each node's ``locations`` array."""
    rows: list[BaselineRow] = []
    if not output or not isinstance(output, dict):
        return rows
    for node_id, payload in output.items():
        if not isinstance(payload, dict):
            continue
        raw_locs = payload.get("locations")
        if raw_locs is None:
            continue
        if isinstance(raw_locs, dict) and "locations" in raw_locs:
            raw_locs = raw_locs.get("locations")
        if not isinstance(raw_locs, list):
            continue
        for i, loc in enumerate(raw_locs):
            if not isinstance(loc, dict):
                continue
            anchor = _anchor_for_place_dict(loc, str(node_id), i)
            rows.append((anchor, str(node_id), i, loc))
    return rows


def _iter_rows_from_places(output: dict[str, Any] | None) -> list[BaselineRow]:
    """``(anchor, node_id, index, place_dict)`` from GeocodeAgent-style ``places`` buckets."""
    rows: list[BaselineRow] = []
    if not output or not isinstance(output, dict):
        return rows
    for node_id, payload in output.items():
        if not isinstance(payload, dict):
            continue
        places = payload.get("places")
        if not isinstance(places, dict):
            continue
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
                    anchor = _anchor_for_place_dict(loc, str(node_id), idx)
                    rows.append((anchor, str(node_id), idx, loc))
                    idx += 1
        for bucket in ("points", "needs_review", "other"):
            items = places.get(bucket)
            if not isinstance(items, list):
                continue
            for loc in items:
                if not isinstance(loc, dict):
                    continue
                anchor = _anchor_for_place_dict(loc, str(node_id), idx)
                rows.append((anchor, str(node_id), idx, loc))
                idx += 1
    return rows


def _merge_baseline_place_rows(output: dict[str, Any] | None) -> list[BaselineRow]:
    """Union ``locations`` and Geocode ``places`` rows; same anchor keeps the last row."""
    merged_by_anchor: dict[str, BaselineRow] = {}
    order: list[str] = []
    for row in _iter_rows_from_locations(output):
        anchor = row[0]
        if anchor not in merged_by_anchor:
            order.append(anchor)
        merged_by_anchor[anchor] = row
    for row in _iter_rows_from_places(output):
        anchor = row[0]
        if anchor not in merged_by_anchor:
            order.append(anchor)
        merged_by_anchor[anchor] = row
    return [merged_by_anchor[a] for a in order]


def _normalize_locations_overlay(
    overlay: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Return ``(by_anchor_patches, user_added_rows)`` from overlay v1."""
    if not overlay or not isinstance(overlay, dict):
        return {}, []
    loc_root = overlay.get("locations")
    if not isinstance(loc_root, dict):
        return {}, []
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
    return patches, user_added


def build_merged_locations_lane(
    *,
    output: dict[str, Any] | None,
    overlay: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build merged location lane + stale overlay anchors.

    Returns ``(merged_locations, stale_overlay_entries)``.
    """
    baseline = _merge_baseline_place_rows(output)
    patches, user_added = _normalize_locations_overlay(overlay)

    merged: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []

    anchors_in_model = {a for a, _nid, _i, _loc in baseline}

    for anchor, node_id, idx, loc in baseline:
        loc_out = copy.deepcopy(loc)
        patch = patches.get(anchor)
        if isinstance(patch, dict) and patch:
            loc_out = _shallow_merge_dict(loc_out, patch)
        merged.append(
            {
                "anchor": anchor,
                "source": "model",
                "node_id": node_id,
                "index_in_node": idx,
                "stale": False,
                "location": loc_out,
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
        merged.append(
            {
                "anchor": rid,
                "source": "user",
                "node_id": None,
                "index_in_node": None,
                "stale": False,
                "location": loc_out,
            }
        )

    return merged, stale
