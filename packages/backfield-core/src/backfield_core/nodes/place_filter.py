"""PlaceFilter node — LLM relevance filtering (vendored runtime)."""

from __future__ import annotations

from typing import Any

from agate_runtime.context import AgateEnvContext
from agate_runtime.runners import run_place_filter_runtime


def run_place_filter(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    ctx = AgateEnvContext()
    return run_place_filter_runtime(params, inputs, ctx)
