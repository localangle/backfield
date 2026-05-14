"""Merge immutable model ``locations`` with review overlay for processed items.

See ``docs/API.md`` → *Processed item location overlay (v1)* for the JSON contract.
"""

from __future__ import annotations

import copy
from typing import Any


def _shallow_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        out[k] = copy.deepcopy(v)
    return out


def _iter_baseline_place_rows(
    output: dict[str, Any] | None,
) -> list[tuple[str, str, int, dict[str, Any]]]:
    """Return ``(anchor, node_id, index, place_dict)`` for each model location row."""
    rows: list[tuple[str, str, int, dict[str, Any]]] = []
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
            aid = loc.get("id")
            if aid is None or aid == "":
                aid = loc.get("mention_id")
            if aid is None or aid == "":
                anchor = f"{node_id}:{i}"
            else:
                anchor = str(aid)
            rows.append((anchor, str(node_id), i, loc))
    return rows


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
    baseline = _iter_baseline_place_rows(output)
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
