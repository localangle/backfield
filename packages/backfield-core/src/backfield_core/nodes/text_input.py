"""TextInput node."""

from __future__ import annotations

from typing import Any


def run_text_input(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    text = params.get("text") or ""
    if not str(text).strip():
        raise ValueError(
            "TextInput node requires non-empty text. "
            "Please add text to the TextInput node before running the flow."
        )
    return {"text": str(text)}
