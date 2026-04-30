"""Output (JSON) — consolidates merged upstream state (agate Output semantics)."""

from __future__ import annotations

from typing import Any

from backfield_agate.runners import run_output_runtime


def run_output(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    return run_output_runtime(inputs, params)
