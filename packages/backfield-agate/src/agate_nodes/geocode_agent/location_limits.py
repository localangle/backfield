"""GeocodeAgent location batching helpers."""

from __future__ import annotations

from typing import Any


def location_needs_review_entry(loc: dict[str, Any], error: str) -> dict[str, Any]:
    """Build a ``needs_review`` row for a location that was not geocoded."""
    location_info = loc.get("location", {})
    if not isinstance(location_info, dict):
        location_info = {}
    return {
        "original_text": loc.get("original_text", ""),
        "location": location_info,
        "error": error,
    }


def split_locations_for_geocoding(
    filtered_locations: list[dict[str, Any]],
    max_locations: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return locations to geocode and overflow rows that exceed ``max_locations``."""
    if len(filtered_locations) <= max_locations:
        return filtered_locations, []
    return filtered_locations[:max_locations], filtered_locations[max_locations:]
