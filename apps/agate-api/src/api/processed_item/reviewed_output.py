"""Materialize reviewed run output (model ``result_json`` + review overlay).

See ``docs/API.md`` → *Reviewed output*. Does not mutate cache or Stylebook.
"""

from __future__ import annotations

import copy
from typing import Any

from api.processed_item_locations_merge import (
    _anchor_for_place_dict,
    _normalize_locations_overlay,
    _select_geocoded_places_node_id,
    build_merged_locations_lane,
)

ARTICLE_OVERLAY_KEYS: tuple[str, ...] = (
    "publication",
    "url",
    "headline",
    "author",
    "pub_date",
)


def overlay_has_review_content(overlay: dict[str, Any] | None) -> bool:
    """True when overlay carries location or article review edits."""
    if not overlay or not isinstance(overlay, dict):
        return False
    loc_root = overlay.get("locations")
    if isinstance(loc_root, dict):
        by_anchor = loc_root.get("by_anchor")
        if isinstance(by_anchor, dict) and len(by_anchor) > 0:
            return True
        user_added = loc_root.get("user_added")
        if isinstance(user_added, list) and len(user_added) > 0:
            return True
        removed = loc_root.get("removed_anchors")
        if isinstance(removed, list):
            for anchor in removed:
                if isinstance(anchor, str) and anchor.strip():
                    return True
    article = overlay.get("article")
    if isinstance(article, dict):
        for key in ARTICLE_OVERLAY_KEYS:
            if key in article:
                return True
    return False


def _apply_merged_places_to_places_bucket(
    places: dict[str, Any],
    *,
    node_id: str,
    anchor_to_location: dict[str, dict[str, Any]],
    removed_anchors: set[str],
    user_locations: list[dict[str, Any]],
) -> dict[str, Any]:
    out = copy.deepcopy(places)
    idx = 0
    areas = out.get("areas")
    if isinstance(areas, dict):
        for bucket in ("states", "counties", "cities", "neighborhoods", "regions", "other"):
            items = areas.get(bucket)
            if not isinstance(items, list):
                continue
            new_items: list[dict[str, Any]] = []
            for loc in items:
                if not isinstance(loc, dict):
                    continue
                anchor = _anchor_for_place_dict(loc, node_id, idx)
                idx += 1
                if anchor in removed_anchors:
                    continue
                if anchor in anchor_to_location:
                    new_items.append(copy.deepcopy(anchor_to_location[anchor]))
                else:
                    new_items.append(copy.deepcopy(loc))
            areas[bucket] = new_items
    for bucket in ("points", "needs_review", "other"):
        items = out.get(bucket)
        if not isinstance(items, list):
            continue
        new_items = []
        for loc in items:
            if not isinstance(loc, dict):
                continue
            anchor = _anchor_for_place_dict(loc, node_id, idx)
            idx += 1
            if anchor in removed_anchors:
                continue
            if anchor in anchor_to_location:
                new_items.append(copy.deepcopy(anchor_to_location[anchor]))
            else:
                new_items.append(copy.deepcopy(loc))
        out[bucket] = new_items
    points = out.get("points")
    if not isinstance(points, list):
        points = []
        out["points"] = points
    for loc in user_locations:
        points.append(copy.deepcopy(loc))
    return out


def _sync_consolidated_places_in_output(
    output: dict[str, Any],
    merged_places: dict[str, Any],
) -> None:
    """Copy canonical merged ``places`` onto every ``consolidated.places`` in node outputs."""
    places_copy = copy.deepcopy(merged_places)
    for payload in output.values():
        if not isinstance(payload, dict):
            continue
        consolidated = payload.get("consolidated")
        if isinstance(consolidated, dict):
            consolidated["places"] = copy.deepcopy(places_copy)


def _article_patch_from_overlay(overlay: dict[str, Any]) -> dict[str, Any]:
    article_raw = overlay.get("article")
    if not isinstance(article_raw, dict):
        return {}
    patch: dict[str, Any] = {}
    for key in ARTICLE_OVERLAY_KEYS:
        if key in article_raw:
            patch[key] = article_raw[key]
    return patch


def _payload_accepts_article_patch(payload: dict[str, Any]) -> bool:
    """True for JSON Output ``consolidated`` shells and hoisted DBOutput-style payloads."""
    if isinstance(payload.get("consolidated"), dict):
        return True
    if any(key in payload for key in ARTICLE_OVERLAY_KEYS):
        return True
    if "article_id" in payload or payload.get("success") is True:
        return True
    places = payload.get("places")
    if isinstance(places, dict) and any(
        key in payload for key in (*ARTICLE_OVERLAY_KEYS, "text", "article_id")
    ):
        return True
    return False


def _json_output_consolidated_places(output: dict[str, Any]) -> dict[str, Any] | None:
    """``json_output.consolidated.places`` bucket when present (JSON Output node)."""
    payload = output.get("json_output")
    if not isinstance(payload, dict):
        return None
    consolidated = payload.get("consolidated")
    if not isinstance(consolidated, dict):
        return None
    places = consolidated.get("places")
    if isinstance(places, dict):
        return places
    return None


def _apply_article_overlay_to_output(
    output: dict[str, Any],
    overlay: dict[str, Any],
) -> None:
    patch = _article_patch_from_overlay(overlay)
    if not patch:
        return
    patch_copy = copy.deepcopy(patch)
    for payload in output.values():
        if not isinstance(payload, dict) or not _payload_accepts_article_patch(payload):
            continue
        consolidated = payload.get("consolidated")
        if isinstance(consolidated, dict):
            consolidated.update(copy.deepcopy(patch_copy))
            continue
        for key, value in patch_copy.items():
            if key in ARTICLE_OVERLAY_KEYS:
                payload[key] = copy.deepcopy(value)


def build_reviewed_output(
    output: dict[str, Any] | None,
    overlay: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return full reviewed node-output dict, or ``None`` when overlay has no review content."""
    if not output or not isinstance(output, dict):
        return None
    if not overlay_has_review_content(overlay):
        return None

    merged_rows, _stale = build_merged_locations_lane(output=output, overlay=overlay)
    _patches, _user_added, removed_anchors = _normalize_locations_overlay(overlay)

    anchor_to_location: dict[str, dict[str, Any]] = {}
    user_locations: list[dict[str, Any]] = []
    for row in merged_rows:
        if not isinstance(row, dict):
            continue
        anchor = row.get("anchor")
        loc = row.get("location")
        if not isinstance(anchor, str) or not isinstance(loc, dict):
            continue
        if row.get("source") == "user":
            user_locations.append(loc)
        else:
            anchor_to_location[anchor] = loc

    reviewed = copy.deepcopy(output)
    node_id = _select_geocoded_places_node_id(reviewed)
    merged_places: dict[str, Any] | None = None
    if node_id:
        payload = reviewed.get(node_id)
        if isinstance(payload, dict) and isinstance(payload.get("places"), dict):
            merged_places = _apply_merged_places_to_places_bucket(
                payload["places"],
                node_id=node_id,
                anchor_to_location=anchor_to_location,
                removed_anchors=removed_anchors,
                user_locations=user_locations,
            )
            payload["places"] = merged_places

    json_places = _json_output_consolidated_places(reviewed)
    if json_places is not None and merged_places is None:
        merged_places = _apply_merged_places_to_places_bucket(
            json_places,
            node_id="json_output",
            anchor_to_location=anchor_to_location,
            removed_anchors=removed_anchors,
            user_locations=user_locations,
        )
        consolidated = reviewed["json_output"]["consolidated"]
        if isinstance(consolidated, dict):
            consolidated["places"] = merged_places

    if merged_places is not None:
        _sync_consolidated_places_in_output(reviewed, merged_places)

    if overlay and isinstance(overlay, dict):
        _apply_article_overlay_to_output(reviewed, overlay)

    return reviewed
