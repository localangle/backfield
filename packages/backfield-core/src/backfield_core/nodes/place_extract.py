"""PlaceExtract node — starter heuristic (no LLM)."""

from __future__ import annotations

import re
from typing import Any

_CITY_STATE = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*),\s*([A-Z]{2})\b",
)


def run_place_extract(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    text = inputs.get("text") or ""
    if not isinstance(text, str):
        text = str(text)
    locations: list[dict[str, Any]] = []
    for m in _CITY_STATE.finditer(text):
        city, st = m.group(1), m.group(2)
        loc = f"{city}, {st}"
        locations.append(
            {
                "location": loc,
                "type": "city",
                "original_text": m.group(0),
                "description": f"Mentioned in text: {loc}",
                "components": {
                    "city": city,
                    "state": {"abbr": st},
                },
            }
        )
    return {"locations": locations}
