"""Scan Agate graph specs for per-node stylebook id references (Issue 2 / multiple stylebooks)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from backfield_db import AgateGraph, BackfieldProject, Stylebook
from sqlmodel import Session, select

# Canonical param key on ``NodeConfig.params`` for catalog stylebook identity (integer DB id).
STYLEBOOK_NODE_PARAM_KEY = "stylebook_id"


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
        sid = _coerce_stylebook_param(params.get(STYLEBOOK_NODE_PARAM_KEY))
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
