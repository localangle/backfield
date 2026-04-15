"""Fix horizontal node positions for Starter flow graphs and Geocode template.

Revision ID: 002_starter_flow_layout
Revises: 002_backfield_identity
Create Date: 2026-04-13

React Flow uses top-left positions. The previous 220px step overlapped TextInput
(w-[280px]) with PlaceExtract. Positions match backfield_core.starter_flow.
"""

from __future__ import annotations

import json
from typing import Any, Union

from alembic import op
from sqlalchemy import text

revision: str = "002_starter_flow_layout"
down_revision: Union[str, None] = "002_backfield_identity"
branch_labels = None
depends_on = None

STARTER_FLOW_GRAPH_NAME = "Starter flow"
STARTER_SPEC_NAME = "starter_geocode_flow"
TEMPLATE_ROW_NAME = "Geocode pipeline"
TEMPLATE_SPEC_NAME = "Geocode pipeline"

_GAP = 48
_TEXT_W = 280
_OTHER_W = 200
_X1 = 0.0
_X2 = _X1 + _TEXT_W + _GAP
_X3 = _X2 + _OTHER_W + _GAP
_X4 = _X3 + _OTHER_W + _GAP

_STARTER_NEW = {
    "n1": {"x": _X1, "y": 0.0},
    "n2": {"x": _X2, "y": 0.0},
    "n3": {"x": _X3, "y": 0.0},
    "n4": {"x": _X4, "y": 0.0},
}
_STARTER_OLD = {
    "n1": {"x": 0.0, "y": 0.0},
    "n2": {"x": 220.0, "y": 0.0},
    "n3": {"x": 440.0, "y": 0.0},
    "n4": {"x": 660.0, "y": 0.0},
}

_TEMPLATE_NEW = {
    "t1": {"x": _X1, "y": 0.0},
    "t2": {"x": _X2, "y": 0.0},
    "t3": {"x": _X3, "y": 0.0},
    "t4": {"x": _X4, "y": 0.0},
}
_TEMPLATE_OLD = {
    "t1": {"x": 0.0, "y": 0.0},
    "t2": {"x": 220.0, "y": 0.0},
    "t3": {"x": 440.0, "y": 0.0},
    "t4": {"x": 660.0, "y": 0.0},
}


def _apply_positions(
    nodes: Any,
    layout: dict[str, dict[str, float]],
) -> bool:
    if not isinstance(nodes, list):
        return False
    changed = False
    for node in nodes:
        if not isinstance(node, dict):
            continue
        nid = node.get("id")
        if isinstance(nid, str) and nid in layout:
            node["position"] = dict(layout[nid])
            changed = True
    return changed


def _maybe_rewrite_starter_graph_spec(spec_json: str, layout: dict[str, dict[str, float]]) -> str | None:
    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError:
        return None
    if spec.get("name") != STARTER_SPEC_NAME:
        return None
    nodes = spec.get("nodes")
    if not _apply_positions(nodes, layout):
        return None
    return json.dumps(spec)


def _maybe_rewrite_template_spec(spec_json: str, layout: dict[str, dict[str, float]]) -> str | None:
    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError:
        return None
    if spec.get("name") != TEMPLATE_SPEC_NAME:
        return None
    nodes = spec.get("nodes")
    if not _apply_positions(nodes, layout):
        return None
    return json.dumps(spec)


def upgrade() -> None:
    bind = op.get_bind()
    graphs = bind.execute(
        text("SELECT id, spec_json FROM agate_graph WHERE name = :name"),
        {"name": STARTER_FLOW_GRAPH_NAME},
    ).all()
    for gid, spec_json in graphs:
        new_json = _maybe_rewrite_starter_graph_spec(spec_json, _STARTER_NEW)
        if new_json is not None:
            bind.execute(
                text("UPDATE agate_graph SET spec_json = :spec WHERE id = :id"),
                {"spec": new_json, "id": gid},
            )

    templates = bind.execute(
        text("SELECT id, spec_json FROM agate_template WHERE name = :name"),
        {"name": TEMPLATE_ROW_NAME},
    ).all()
    for tid, spec_json in templates:
        new_json = _maybe_rewrite_template_spec(spec_json, _TEMPLATE_NEW)
        if new_json is not None:
            bind.execute(
                text("UPDATE agate_template SET spec_json = :spec WHERE id = :id"),
                {"spec": new_json, "id": tid},
            )


def downgrade() -> None:
    bind = op.get_bind()
    graphs = bind.execute(
        text("SELECT id, spec_json FROM agate_graph WHERE name = :name"),
        {"name": STARTER_FLOW_GRAPH_NAME},
    ).all()
    for gid, spec_json in graphs:
        new_json = _maybe_rewrite_starter_graph_spec(spec_json, _STARTER_OLD)
        if new_json is not None:
            bind.execute(
                text("UPDATE agate_graph SET spec_json = :spec WHERE id = :id"),
                {"spec": new_json, "id": gid},
            )

    templates = bind.execute(
        text("SELECT id, spec_json FROM agate_template WHERE name = :name"),
        {"name": TEMPLATE_ROW_NAME},
    ).all()
    for tid, spec_json in templates:
        new_json = _maybe_rewrite_template_spec(spec_json, _TEMPLATE_OLD)
        if new_json is not None:
            bind.execute(
                text("UPDATE agate_template SET spec_json = :spec WHERE id = :id"),
                {"spec": new_json, "id": tid},
            )
