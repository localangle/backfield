"""Tests for run graph spec snapshot helpers."""

from __future__ import annotations

import json

from agate_runtime.run_graph_spec import (
    GRAPH_SPEC_JSON_KEY,
    merge_run_result_payload,
    resolve_run_graph_spec_json,
)


def test_merge_run_result_payload_preserves_existing_sections() -> None:
    merged = merge_run_result_payload(
        json.dumps({"s3_batch": {"valid_executed": 3}}),
        **{GRAPH_SPEC_JSON_KEY: '{"name":"flow"}'},
    )
    data = json.loads(merged)
    assert data["s3_batch"]["valid_executed"] == 3
    assert data[GRAPH_SPEC_JSON_KEY] == '{"name":"flow"}'


def test_resolve_run_graph_spec_json_prefers_snapshot() -> None:
    live = '{"name":"live"}'
    snap = json.dumps({GRAPH_SPEC_JSON_KEY: '{"name":"snap"}'})
    resolved = resolve_run_graph_spec_json(run_result_json=snap, graph_spec_json=live)
    assert resolved == '{"name":"snap"}'


def test_resolve_run_graph_spec_json_falls_back_to_live_graph() -> None:
    live = '{"name":"live"}'
    resolved = resolve_run_graph_spec_json(run_result_json=None, graph_spec_json=live)
    assert resolved == live
