"""Coerce inconsistent PlaceExtract LLM location objects before validation."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def coerce_llm_location_entry(location_data: dict[str, Any]) -> dict[str, Any]:
    """Normalize one LLM location object (nested location dict, missing components, etc.)."""
    data = dict(location_data)
    loc = data.get("location")
    if isinstance(loc, dict):
        nested_full = loc.get("full") or loc.get("location") or ""
        if isinstance(nested_full, str):
            data["location"] = nested_full
        elif nested_full is not None:
            data["location"] = str(nested_full)
        else:
            data["location"] = ""
        if "type" not in data and loc.get("type") is not None:
            data["type"] = loc.get("type")
        nested_components = loc.get("components")
        if "components" not in data and isinstance(nested_components, dict):
            data["components"] = nested_components

    components = data.get("components")
    if components is None or "components" not in data:
        logger.warning(
            "[PlaceExtract] LLM location entry missing components; defaulting to empty dict "
            "(location=%r type=%r)",
            data.get("location"),
            data.get("type"),
        )
        data["components"] = {}
    elif not isinstance(components, dict):
        logger.warning(
            "[PlaceExtract] LLM location components is %s, not a dict; defaulting to empty dict",
            type(components).__name__,
        )
        data["components"] = {}
    return data
