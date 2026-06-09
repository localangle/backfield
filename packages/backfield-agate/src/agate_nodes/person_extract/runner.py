"""PersonExtract runner for the Backfield executor."""

from __future__ import annotations

from typing import Any

from agate_runtime.runners import default_context, run_person_extract_runtime


def run_person_extract(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    return run_person_extract_runtime(params, inputs, default_context())
