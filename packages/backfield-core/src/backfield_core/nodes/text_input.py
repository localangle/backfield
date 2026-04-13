"""TextInput node."""

from __future__ import annotations

from typing import Any


def run_text_input(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    text = params.get("text") or inputs.get("text") or ""
    return {"text": str(text)}
