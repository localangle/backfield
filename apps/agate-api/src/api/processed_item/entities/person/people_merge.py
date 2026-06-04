"""Merge immutable model ``people`` with review overlay for processed items."""

from __future__ import annotations

import copy
from typing import Any

from api.processed_item.mention_occurrences import (
    build_mention_occurrences_for_row,
    occurrences_from_place_dict,
)

BaselineRow = tuple[str, str, int, dict[str, Any]]

_PEOPLE_NODE_PRIORITY: tuple[str, ...] = (
    "stylebook_output",
    "stylebook-output",
    "DBOutput",
    "db_output",
)

_PERSON_EXTRACT_NODE_IDS: frozenset[str] = frozenset(
    {"person_extract", "PersonExtract"},
)


def _node_ids_with_people(output: dict[str, Any] | None) -> frozenset[str]:
    ids: set[str] = set()
    if not output or not isinstance(output, dict):
        return frozenset()
    for node_id, payload in output.items():
        if isinstance(payload, dict) and isinstance(payload.get("people"), list):
            ids.add(str(node_id))
    return frozenset(ids)


def _people_node_candidates(output: dict[str, Any] | None) -> frozenset[str]:
    excluded_lower = {n.lower() for n in _PERSON_EXTRACT_NODE_IDS}
    return frozenset(
        n
        for n in _node_ids_with_people(output)
        if n not in _PERSON_EXTRACT_NODE_IDS and n.lower() not in excluded_lower
    )


def _select_people_node_id(output: dict[str, Any] | None) -> str | None:
    candidates = _people_node_candidates(output)
    if not candidates:
        return None
    node_set = {str(n) for n in candidates}
    for pref in _PEOPLE_NODE_PRIORITY:
        if pref in node_set:
            return pref
    lower_map = {n.lower(): n for n in node_set}
    for pref in _PEOPLE_NODE_PRIORITY:
        hit = lower_map.get(pref.lower())
        if hit:
            return hit
    return sorted(node_set)[0]


def _shallow_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        out[k] = copy.deepcopy(v)
    return out


def _anchor_for_person_dict(person: dict[str, Any], node_id: str, index: int) -> str:
    for key in ("id", "mention_id"):
        raw = person.get(key)
        if raw is None:
            continue
        s = str(raw).strip()
        if s:
            return s
    return f"{node_id}:{index}"


def _iter_rows_from_people_node(
    output: dict[str, Any],
    node_id: str,
) -> list[BaselineRow]:
    rows: list[BaselineRow] = []
    payload = output.get(node_id)
    if not isinstance(payload, dict):
        return rows
    people = payload.get("people")
    if not isinstance(people, list):
        return rows
    for idx, person in enumerate(people):
        if not isinstance(person, dict):
            continue
        anchor = _anchor_for_person_dict(person, node_id, idx)
        rows.append((anchor, node_id, idx, person))
    return rows


def _merge_baseline_people_rows(output: dict[str, Any] | None) -> list[BaselineRow]:
    node_id = _select_people_node_id(output)
    if not node_id or not output:
        return []
    return _iter_rows_from_people_node(output, node_id)


def _normalize_people_overlay(
    overlay: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    if not overlay or not isinstance(overlay, dict):
        return {}, [], set()
    root = overlay.get("people")
    if not isinstance(root, dict):
        return {}, [], set()
    patches_raw = root.get("by_anchor")
    patches: dict[str, Any] = {}
    if isinstance(patches_raw, dict):
        for k, v in patches_raw.items():
            if isinstance(k, str) and isinstance(v, dict):
                patches[k] = v
    user_added: list[dict[str, Any]] = []
    ua_raw = root.get("user_added")
    if isinstance(ua_raw, list):
        for row in ua_raw:
            if isinstance(row, dict):
                user_added.append(row)
    removed: set[str] = set()
    removed_raw = root.get("removed_anchors")
    if isinstance(removed_raw, list):
        for anchor in removed_raw:
            if isinstance(anchor, str) and anchor.strip():
                removed.add(anchor.strip())
    return patches, user_added, removed


def build_merged_people_lane(
    *,
    output: dict[str, Any] | None,
    overlay: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build merged people lane + stale overlay anchors."""
    baseline = _merge_baseline_people_rows(output)
    patches, user_added, removed_anchors = _normalize_people_overlay(overlay)

    merged: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []

    anchors_in_model = {a for a, _nid, _i, _person in baseline}

    for anchor, node_id, idx, person in baseline:
        if anchor in removed_anchors:
            continue
        person_out = copy.deepcopy(person)
        patch = patches.get(anchor)
        patch_dict = patch if isinstance(patch, dict) else None
        if patch_dict:
            person_out = _shallow_merge_dict(person_out, patch_dict)
        mention_occurrences = build_mention_occurrences_for_row(
            place=person_out,
            overlay_patch=patch_dict,
            db_rows=None,
        )
        merged.append(
            {
                "anchor": anchor,
                "source": "model",
                "node_id": node_id,
                "index_in_node": idx,
                "stale": False,
                "person": person_out,
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
        if not isinstance(rid, str) or not rid.startswith("user_person:"):
            continue
        person_payload = row.get("person")
        if isinstance(person_payload, dict):
            person_out = copy.deepcopy(person_payload)
        else:
            rest = {k: v for k, v in row.items() if k not in ("id", "person")}
            person_out = rest if rest else {}
        patch = patches.get(rid)
        if isinstance(patch, dict):
            person_out = _shallow_merge_dict(person_out, patch)
        mention_occurrences = build_mention_occurrences_for_row(
            place=person_out,
            overlay_patch=None,
            db_rows=None,
        )
        merged.append(
            {
                "anchor": rid,
                "source": "user",
                "node_id": None,
                "index_in_node": None,
                "stale": False,
                "person": person_out,
                "mention_occurrences": mention_occurrences,
            }
        )

    return merged, stale


def normalize_people_overlay(
    overlay: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    """Public wrapper for reviewed-output materialization."""
    return _normalize_people_overlay(overlay)


def select_people_node_id(output: dict[str, Any] | None) -> str | None:
    """Public wrapper for reviewed-output materialization."""
    return _select_people_node_id(output)


def occurrences_from_person_dict(person: dict[str, Any]) -> list[dict[str, Any]]:
    """Reuse place occurrence builder (person rows use the same ``mentions`` shape)."""
    return occurrences_from_place_dict(person)
