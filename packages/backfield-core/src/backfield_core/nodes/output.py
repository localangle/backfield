"""Output (JSON) — consolidates upstream data into a JSON object."""

from __future__ import annotations

from typing import Any


def run_output(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    data = inputs.get("data")
    return {"consolidated": data}
