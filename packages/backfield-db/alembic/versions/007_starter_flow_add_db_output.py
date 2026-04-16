"""Add DBOutput to Starter flow graph specs (persistence gate).

Revision ID: 007_starter_flow_add_db_output
Revises: 006_article_source_run_id_text
"""

from __future__ import annotations

import json
from typing import Any, Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "007_starter_flow_add_db_output"
down_revision: Union[str, None] = "006_article_source_run_id_text"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STARTER_FLOW_GRAPH_NAME = "Starter flow"
STARTER_SPEC_NAME = "starter_geocode_flow"


def _needs_rewrite(spec: dict[str, Any]) -> bool:
    if spec.get("name") != STARTER_SPEC_NAME:
        return False
    nodes = spec.get("nodes")
    if not isinstance(nodes, list):
        return False
    types = {n.get("type") for n in nodes if isinstance(n, dict)}
    if "DBOutput" in types:
        return False
    return True


def upgrade() -> None:
    # Import inside migration to avoid import-order surprises for offline environments.
    from backfield_core import starter_geocode_flow_graph_spec

    canonical = starter_geocode_flow_graph_spec().model_dump(mode="json")
    canonical_json = json.dumps(canonical)

    bind = op.get_bind()
    rows = bind.execute(
        text("SELECT id, spec_json FROM agate_graph WHERE name = :name"),
        {"name": STARTER_FLOW_GRAPH_NAME},
    ).all()
    for gid, spec_json in rows:
        try:
            spec = json.loads(spec_json)
        except json.JSONDecodeError:
            continue
        if not _needs_rewrite(spec):
            continue
        bind.execute(
            text("UPDATE agate_graph SET spec_json = :spec WHERE id = :id"),
            {"spec": canonical_json, "id": gid},
        )


def downgrade() -> None:
    # Non-reversible: we cannot reliably reconstruct prior per-user edits.
    pass
