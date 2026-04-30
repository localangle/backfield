"""PlaceExtract node — LLM extraction (vendored runtime)."""

from __future__ import annotations

from typing import Any

from backfield_agate.context import AgateEnvContext
from backfield_agate.runners import run_place_extract_runtime


def run_place_extract(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    ctx = AgateEnvContext()
    return run_place_extract_runtime(params, inputs, ctx)
