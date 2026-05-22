"""Parse one PlaceExtract LLM location entry into a ``Place`` (no executor imports)."""

from __future__ import annotations

from typing import Any

from agate_nodes.place_extract.llm_location_coerce import coerce_llm_location_entry
from agate_nodes.place_extract.mentions import normalize_location_mentions
from agate_nodes.place_extract.place_schemas import (
    CountryInfo,
    LocationComponents,
    LocationInfo,
    Place,
    PlaceInfo,
    PlaceMention,
    SpanEndpoint,
    SpanInfo,
    StateInfo,
    StreetRoadInfo,
)


def _normalize_components_dict(components_data: dict[str, Any]) -> dict[str, Any]:
    """Coerce optional component sub-objects before ``LocationComponents`` validation."""
    components = dict(components_data)

    if components.get("place"):
        place_data = components["place"]
        if isinstance(place_data, dict) and place_data.get("name"):
            try:
                components["place"] = PlaceInfo(**place_data)
            except Exception:
                components["place"] = None
        else:
            components["place"] = None
    else:
        components["place"] = None

    if components.get("street_road"):
        street_road_data = components["street_road"]
        if (
            isinstance(street_road_data, dict)
            and street_road_data.get("name")
            and street_road_data.get("boundary")
        ):
            components["street_road"] = StreetRoadInfo(**street_road_data)
        else:
            components["street_road"] = None
    else:
        components["street_road"] = None

    if components.get("span"):
        span_data = components["span"]
        if isinstance(span_data, dict):
            try:
                start = span_data.get("start")
                end = span_data.get("end")
                components["span"] = SpanInfo(
                    start=SpanEndpoint(**start)
                    if isinstance(start, dict) and start.get("type") and start.get("location")
                    else None,
                    end=SpanEndpoint(**end)
                    if isinstance(end, dict) and end.get("type") and end.get("location")
                    else None,
                )
            except Exception:
                components["span"] = None
        else:
            components["span"] = None
    else:
        components["span"] = None

    if components.get("state"):
        state_data = components["state"]
        if isinstance(state_data, dict) and state_data.get("name") and state_data.get("abbr"):
            components["state"] = StateInfo(**state_data)
        else:
            components["state"] = None
    else:
        components["state"] = None

    if components.get("country"):
        country_data = components["country"]
        if isinstance(country_data, dict) and country_data.get("name") and country_data.get("abbr"):
            components["country"] = CountryInfo(**country_data)
        else:
            components["country"] = None
    else:
        components["country"] = None

    return components


def place_from_llm_location_entry(location_data: dict[str, Any]) -> Place:
    """Parse one coerced LLM location dict into a ``Place`` (raises on hard failures)."""
    location_data = coerce_llm_location_entry(location_data)

    required_fields = ["original_text", "description", "location", "type"]
    for field in required_fields:
        if field not in location_data:
            raise ValueError(f"Missing required field '{field}' in location data")

    location_str = location_data["location"]
    location_type = location_data["type"]
    components_data = location_data["components"]

    if not isinstance(location_str, str):
        raise ValueError("Location field must be a string")
    if not isinstance(location_type, str):
        raise ValueError("Type field must be a string")
    if not isinstance(components_data, dict):
        raise ValueError("Components field must be a dictionary")

    location_components = LocationComponents(**_normalize_components_dict(components_data))
    location_info_obj = LocationInfo(
        full=location_str,
        type=location_type,
        components=location_components,
    )

    normalized = normalize_location_mentions(location_data)
    place_data: dict[str, Any] = {
        "original_text": normalized["original_text"],
        "description": normalized["description"],
        "location": location_info_obj,
        "mentions": [
            PlaceMention(**m) for m in normalized.get("mentions", []) if isinstance(m, dict)
        ],
    }
    for key, value in normalized.items():
        if key not in ["original_text", "description", "location", "type", "components", "mentions"]:
            place_data[key] = value
    return Place(**place_data)
