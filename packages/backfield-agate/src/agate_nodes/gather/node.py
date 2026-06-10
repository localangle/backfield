"""Gather node — passthrough namespaced upstream state for downstream nodes."""

from __future__ import annotations

from typing import Any


def run_gather(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Return consolidated upstream outputs keyed by source node id under ``gathered``."""
    return {"gathered": dict(inputs)}
