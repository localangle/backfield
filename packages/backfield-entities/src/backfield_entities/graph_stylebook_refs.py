"""Scan Agate graph specs for per-node stylebook id references (Issue 2 / multiple stylebooks)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from backfield_db import AgateGraph, BackfieldProject, Stylebook
from sqlmodel import Session, select

# Canonical param key on ``NodeConfig.params`` for catalog stylebook identity (integer DB id).
STYLEBOOK_NODE_PARAM_KEY = "stylebook_id"
# Legacy camelCase used by older GeocodeAgent panels — still counted for validation / impact.
_LEGACY_STYLEBOOK_PARAM_KEY = "stylebookId"


class StylebookGraphRefsError(ValueError):
    """Raised when a graph references a missing or out-of-org stylebook."""


def _coerce_stylebook_param(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        if raw != raw or raw % 1 != 0:  # nan or non-whole
            return None
        return int(raw)
    if isinstance(raw, str):
        s = raw.strip()
        if not s or not s.isdigit():
            return None
        return int(s)
    return None


def stylebook_id_from_node_params(params: Mapping[str, Any]) -> int | None:
    """Resolve stylebook id from node params (canonical key first, then legacy camelCase)."""
    if not isinstance(params, dict):
        return None
    sid = _coerce_stylebook_param(params.get(STYLEBOOK_NODE_PARAM_KEY))
    if sid is not None:
        return sid
    return _coerce_stylebook_param(params.get(_LEGACY_STYLEBOOK_PARAM_KEY))


def iter_stylebook_refs_from_spec_dict(spec: Mapping[str, Any]) -> list[tuple[str, int]]:
    """Return ``(node_id, stylebook_id)`` for each node whose params set ``stylebook_id``."""
    out: list[tuple[str, int]] = []
    nodes = spec.get("nodes")
    if not isinstance(nodes, list):
        return out
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        params = node.get("params")
        if not isinstance(nid, str) or not isinstance(params, dict):
            continue
        sid = stylebook_id_from_node_params(params)
        if sid is not None:
            out.append((nid, sid))
    return out


def unique_stylebook_ids_from_spec_dict(spec: Mapping[str, Any]) -> list[int]:
    """Ordered unique stylebook ids referenced by the spec (stable order)."""
    seen: set[int] = set()
    ordered: list[int] = []
    for _, sid in iter_stylebook_refs_from_spec_dict(spec):
        if sid not in seen:
            seen.add(sid)
            ordered.append(sid)
    return ordered


def validate_stylebook_refs_for_organization(
    session: Session,
    *,
    organization_id: int,
    spec: Mapping[str, Any],
) -> None:
    """Ensure every referenced stylebook id exists and belongs to ``organization_id``."""
    for sid in unique_stylebook_ids_from_spec_dict(spec):
        sb = session.get(Stylebook, sid)
        if sb is None:
            raise StylebookGraphRefsError(
                "This flow references a stylebook that no longer exists. "
                "Update the affected nodes to use a valid stylebook.",
            )
        if int(sb.organization_id) != int(organization_id):
            raise StylebookGraphRefsError(
                "This flow references a stylebook that is not part of your organization. "
                "Update the affected nodes to use a valid stylebook.",
            )


def _stylebook_ids_for_organization(session: Session, organization_id: int) -> set[int]:
    rows = session.exec(
        select(Stylebook.id).where(Stylebook.organization_id == organization_id)
    ).all()
    return {int(row) for row in rows if row is not None}


def _org_default_stylebook_id(session: Session, organization_id: int) -> int | None:
    row = session.exec(
        select(Stylebook.id).where(
            Stylebook.organization_id == organization_id,
            Stylebook.is_default.is_(True),
        )
    ).first()
    return int(row) if row is not None else None


def _apply_stylebook_ref_replacement(params: dict[str, Any], *, replacement: int | None) -> None:
    if replacement is None:
        params.pop(STYLEBOOK_NODE_PARAM_KEY, None)
        params.pop(_LEGACY_STYLEBOOK_PARAM_KEY, None)
        return
    params[STYLEBOOK_NODE_PARAM_KEY] = replacement
    params.pop(_LEGACY_STYLEBOOK_PARAM_KEY, None)


def _is_db_output_node_type(node_type: Any) -> bool:
    if not isinstance(node_type, str):
        return False
    normalized = node_type.strip().lower().replace("-", "_")
    return normalized in ("dboutput", "db_output")


def _is_geocode_agent_node_type(node_type: Any) -> bool:
    if not isinstance(node_type, str):
        return False
    normalized = node_type.strip().lower().replace("-", "_")
    return normalized in ("geocodeagent", "geocode_agent")


def sanitize_stylebook_refs_for_organization(
    session: Session,
    *,
    organization_id: int,
    spec: dict[str, Any],
) -> bool:
    """Replace missing stylebook ids with the org default (or clear for Backfield output).

    Returns ``True`` when ``spec`` was mutated. Cross-org references are left unchanged so
    validation can still reject them explicitly.
    """
    valid_ids = _stylebook_ids_for_organization(session, organization_id)
    if not valid_ids:
        return False
    default_id = _org_default_stylebook_id(session, organization_id)

    nodes = spec.get("nodes")
    if not isinstance(nodes, list):
        return False

    changed = False
    for node in nodes:
        if not isinstance(node, dict):
            continue
        params = node.get("params")
        if not isinstance(params, dict):
            continue
        sid = stylebook_id_from_node_params(params)
        if sid is None or sid in valid_ids:
            continue
        sb = session.get(Stylebook, sid)
        if sb is not None and int(sb.organization_id) != int(organization_id):
            continue

        node_type = node.get("type")
        if _is_db_output_node_type(node_type):
            _apply_stylebook_ref_replacement(params, replacement=None)
        elif _is_geocode_agent_node_type(node_type):
            use_cache = params.get("useCache")
            if use_cache is True and default_id is not None:
                _apply_stylebook_ref_replacement(params, replacement=default_id)
            else:
                _apply_stylebook_ref_replacement(params, replacement=None)
        elif default_id is not None:
            _apply_stylebook_ref_replacement(params, replacement=default_id)
        else:
            _apply_stylebook_ref_replacement(params, replacement=None)
        changed = True
    return changed


def reassign_stylebook_id_in_spec_dict(
    spec: dict[str, Any],
    *,
    from_stylebook_id: int,
    to_stylebook_id: int,
) -> bool:
    """Replace ``from_stylebook_id`` with ``to_stylebook_id`` in every node params.

    Returns ``True`` when the spec was mutated.
    """
    if from_stylebook_id == to_stylebook_id:
        return False
    nodes = spec.get("nodes")
    if not isinstance(nodes, list):
        return False
    changed = False
    for node in nodes:
        if not isinstance(node, dict):
            continue
        params = node.get("params")
        if not isinstance(params, dict):
            continue
        sid = stylebook_id_from_node_params(params)
        if sid != from_stylebook_id:
            continue
        params[STYLEBOOK_NODE_PARAM_KEY] = to_stylebook_id
        if _LEGACY_STYLEBOOK_PARAM_KEY in params:
            params[_LEGACY_STYLEBOOK_PARAM_KEY] = to_stylebook_id
        changed = True
    return changed


def reassign_stylebook_refs_in_org_graphs(
    session: Session,
    *,
    organization_id: int,
    from_stylebook_id: int,
    to_stylebook_id: int,
) -> int:
    """Rewrite graph specs when a stylebook is deleted.

    Returns the number of graphs whose ``spec_json`` was updated.
    """
    if from_stylebook_id == to_stylebook_id:
        return 0
    graphs = session.exec(
        select(AgateGraph, BackfieldProject)
        .join(BackfieldProject, AgateGraph.project_id == BackfieldProject.id)
        .where(BackfieldProject.organization_id == organization_id)
    ).all()

    updated = 0
    for ag, _proj in graphs:
        try:
            spec = json.loads(ag.spec_json)
        except json.JSONDecodeError:
            continue
        if not isinstance(spec, dict):
            continue
        if reassign_stylebook_id_in_spec_dict(
            spec,
            from_stylebook_id=from_stylebook_id,
            to_stylebook_id=to_stylebook_id,
        ):
            ag.spec_json = json.dumps(spec)
            session.add(ag)
            updated += 1
    if updated:
        session.flush()
    return updated


def count_stylebook_usage_in_graphs(
    session: Session,
    *,
    organization_id: int,
    stylebook_id: int,
) -> tuple[int, int]:
    """Count graphs and node references to ``stylebook_id`` under all projects in the org.

    Returns ``(graph_count, node_reference_count)``. A graph is counted once if at least one
    node references the stylebook; ``node_reference_count`` counts each node that does (so
    duplicates if multiple nodes reference the same book).
    """
    graphs = session.exec(
        select(AgateGraph, BackfieldProject)
        .join(BackfieldProject, AgateGraph.project_id == BackfieldProject.id)
        .where(BackfieldProject.organization_id == organization_id)
    ).all()

    graph_hits = 0
    node_hits = 0
    for ag, _proj in graphs:
        try:
            spec = json.loads(ag.spec_json)
        except json.JSONDecodeError:
            continue
        if not isinstance(spec, dict):
            continue
        refs = iter_stylebook_refs_from_spec_dict(spec)
        local = [(nid, sid) for nid, sid in refs if sid == stylebook_id]
        if local:
            graph_hits += 1
            node_hits += len(local)
    return graph_hits, node_hits
