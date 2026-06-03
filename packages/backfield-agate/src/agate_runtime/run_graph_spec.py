"""Pin graph ``spec_json`` on ``agate_run.result_json`` for consistent batch execution."""

from __future__ import annotations

import json
from typing import Any

GRAPH_SPEC_JSON_KEY = "graph_spec_json"


def parse_run_result_payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def merge_run_result_payload(existing: str | None, **updates: Any) -> str:
    """Merge keys into the run ``result_json`` object without dropping existing sections."""
    data = parse_run_result_payload(existing)
    data.update(updates)
    return json.dumps(data)


def resolve_run_graph_spec_json(*, run_result_json: str | None, graph_spec_json: str) -> str:
    """Use the spec snapshot stored on the run when present."""
    snap = parse_run_result_payload(run_result_json).get(GRAPH_SPEC_JSON_KEY)
    if isinstance(snap, str) and snap.strip():
        return snap
    return graph_spec_json
