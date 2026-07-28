"""GeocodeAgent location batching helpers."""

from __future__ import annotations

from typing import Any, Literal

NeedsReviewReason = Literal[
    "unsupported_location_type",
    "max_locations_exceeded",
    "celery_timeout",
    "geocoding_timeout",
    "geocoding_error",
    "empty_geocoding_result",
]


def location_needs_review_entry(
    loc: dict[str, Any],
    error: str,
    reason_code: NeedsReviewReason,
) -> dict[str, Any]:
    """Build a ``needs_review`` row for a location that was not geocoded."""
    location_info = loc.get("location", {})
    if not isinstance(location_info, dict):
        location_info = {}
    return {
        **loc,
        "original_text": loc.get("original_text", ""),
        "location": location_info,
        "error": error,
        "reason_code": reason_code,
    }


def split_locations_for_geocoding(
    filtered_locations: list[dict[str, Any]],
    max_locations: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return locations to geocode and overflow rows that exceed ``max_locations``."""
    if len(filtered_locations) <= max_locations:
        return filtered_locations, []
    return filtered_locations[:max_locations], filtered_locations[max_locations:]
