"""Merge immutable model ``organizations`` with review overlay for processed items."""

from __future__ import annotations

import copy
from typing import Any

from api.processed_item.mention_occurrences import (
    build_mention_occurrences_for_row,
    occurrences_from_place_dict,
)

BaselineRow = tuple[str, str, int, dict[str, Any]]

_ORGANIZATIONS_NODE_PRIORITY: tuple[str, ...] = (
    "stylebook_output",
    "stylebook-output",
    "DBOutput",
    "db_output",
)

_ORGANIZATION_EXTRACT_NODE_IDS: frozenset[str] = frozenset(
    {"organization_extract", "OrganizationExtract"},
)


def _node_ids_with_organizations(output: dict[str, Any] | None) -> frozenset[str]:
    ids: set[str] = set()
    if not output or not isinstance(output, dict):
        return frozenset()
    for node_id, payload in output.items():
        if isinstance(payload, dict) and isinstance(payload.get("organizations"), list):
            ids.add(str(node_id))
    return frozenset(ids)


def _organizations_node_candidates(output: dict[str, Any] | None) -> frozenset[str]:
    excluded_lower = {n.lower() for n in _ORGANIZATION_EXTRACT_NODE_IDS}
    return frozenset(
        n
        for n in _node_ids_with_organizations(output)
        if n not in _ORGANIZATION_EXTRACT_NODE_IDS and n.lower() not in excluded_lower
    )


def _select_organizations_node_id(output: dict[str, Any] | None) -> str | None:
    candidates = _organizations_node_candidates(output)
    if not candidates:
        return None
    node_set = {str(n) for n in candidates}
    for pref in _ORGANIZATIONS_NODE_PRIORITY:
        if pref in node_set:
            return pref
    lower_map = {n.lower(): n for n in node_set}
    for pref in _ORGANIZATIONS_NODE_PRIORITY:
        hit = lower_map.get(pref.lower())
        if hit:
            return hit
    return sorted(node_set)[0]


def _shallow_merge_dict(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in patch.items():
        out[k] = copy.deepcopy(v)
    return out


def _anchor_for_organization_dict(
    organization: dict[str, Any], node_id: str, index: int
) -> str:
    for key in ("id", "mention_id"):
        raw = organization.get(key)
        if raw is None:
            continue
        s = str(raw).strip()
        if s:
            return s
    return f"{node_id}:{index}"


def _iter_rows_from_organizations_list(
    organizations: list[Any],
    *,
    node_id: str,
) -> list[BaselineRow]:
    rows: list[BaselineRow] = []
    for idx, organization in enumerate(organizations):
        if not isinstance(organization, dict):
            continue
        anchor = _anchor_for_organization_dict(organization, node_id, idx)
        rows.append((anchor, node_id, idx, organization))
    return rows


def _iter_rows_from_organizations_node(
    output: dict[str, Any],
    node_id: str,
) -> list[BaselineRow]:
    payload = output.get(node_id)
    if not isinstance(payload, dict):
        return []
    organizations = payload.get("organizations")
    if not isinstance(organizations, list):
        return []
    return _iter_rows_from_organizations_list(organizations, node_id=node_id)


def json_output_consolidated_organizations(
    output: dict[str, Any] | None,
) -> list[dict[str, Any]] | None:
    """``json_output.consolidated.organizations`` when present (JSON Output node)."""
    if not output or not isinstance(output, dict):
        return None
    payload = output.get("json_output")
    if not isinstance(payload, dict):
        return None
    consolidated = payload.get("consolidated")
    if not isinstance(consolidated, dict):
        return None
    organizations = consolidated.get("organizations")
    if isinstance(organizations, list):
        return organizations
    return None


def _merge_baseline_organizations_rows(output: dict[str, Any] | None) -> list[BaselineRow]:
    if not output:
        return []
    node_id = _select_organizations_node_id(output)
    if node_id:
        return _iter_rows_from_organizations_node(output, node_id)
    json_organizations = json_output_consolidated_organizations(output)
    if json_organizations is not None:
        return _iter_rows_from_organizations_list(json_organizations, node_id="json_output")
    return []


def _normalize_organizations_overlay(
    overlay: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    if not overlay or not isinstance(overlay, dict):
        return {}, [], set()
    root = overlay.get("organizations")
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


def build_merged_organizations_lane(
    *,
    output: dict[str, Any] | None,
    overlay: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build merged organizations lane + stale overlay anchors."""
    baseline = _merge_baseline_organizations_rows(output)
    patches, user_added, removed_anchors = _normalize_organizations_overlay(overlay)

    merged: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []

    anchors_in_model = {a for a, _nid, _i, _organization in baseline}

    for anchor, node_id, idx, organization in baseline:
        if anchor in removed_anchors:
            continue
        organization_out = copy.deepcopy(organization)
        patch = patches.get(anchor)
        patch_dict = patch if isinstance(patch, dict) else None
        if patch_dict:
            organization_out = _shallow_merge_dict(organization_out, patch_dict)
        mention_occurrences = build_mention_occurrences_for_row(
            place=organization_out,
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
                "organization": organization_out,
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
        if not isinstance(rid, str) or not rid.startswith("user_organization:"):
            continue
        organization_payload = row.get("organization")
        if isinstance(organization_payload, dict):
            organization_out = copy.deepcopy(organization_payload)
        else:
            rest = {k: v for k, v in row.items() if k not in ("id", "organization")}
            organization_out = rest if rest else {}
        patch = patches.get(rid)
        if isinstance(patch, dict):
            organization_out = _shallow_merge_dict(organization_out, patch)
        mention_occurrences = build_mention_occurrences_for_row(
            place=organization_out,
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
                "organization": organization_out,
                "mention_occurrences": mention_occurrences,
            }
        )

    return merged, stale


def normalize_organizations_overlay(
    overlay: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[dict[str, Any]], set[str]]:
    """Public wrapper for reviewed-output materialization."""
    return _normalize_organizations_overlay(overlay)


def select_organizations_node_id(output: dict[str, Any] | None) -> str | None:
    """Public wrapper for reviewed-output materialization."""
    return _select_organizations_node_id(output)


def occurrences_from_organization_dict(organization: dict[str, Any]) -> list[dict[str, Any]]:
    """Reuse place occurrence builder (organization rows use the same ``mentions`` shape)."""
    return occurrences_from_place_dict(organization)
