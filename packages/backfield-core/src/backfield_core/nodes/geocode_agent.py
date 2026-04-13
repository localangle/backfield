"""GeocodeAgent — LangGraph + LLM geocoding (vendored runtime)."""

from __future__ import annotations

from typing import Any

from backfield_agate_runtime.context import AgateEnvContext
from backfield_agate_runtime.runners import run_geocode_agent_runtime


def run_geocode_agent(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    ctx = AgateEnvContext()
    return run_geocode_agent_runtime(params, inputs, ctx)
