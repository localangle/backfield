"""Tests for Gather node passthrough."""

from __future__ import annotations

from agate_nodes.gather.node import run_gather


def test_run_gather_passthrough_namespaced_inputs() -> None:
    inputs = {
        "org": {"organizations": [{"name": "City Hall"}]},
        "plc": {"locations": [{"location": "Chicago, IL"}]},
    }
    out = run_gather({}, inputs)
    assert out == {"gathered": inputs}
