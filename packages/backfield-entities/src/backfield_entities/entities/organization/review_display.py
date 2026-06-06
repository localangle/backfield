"""Human-readable review context for organization canonical deferrals."""

from __future__ import annotations

from typing import Any

ORGANIZATION_CANONICAL_TYPE_MISMATCH_MESSAGE = (
    "Could not find Stylebook entry with matching type."
)

_BOUNDARY_DISPLAY_MESSAGES: dict[str, str] = {
    "brand_platform": (
        "Brand or platform mention; confirm this refers to an organization, "
        "not just a service, product, or brand."
    ),
    "work_title": (
        "Work or title mention; confirm this refers to an organization, "
        "not a creative work or publication title."
    ),
    "place_business": (
        "Business or venue mention; confirm this refers to people or operations, "
        "not just a location."
    ),
    "event_competition": (
        "Event or competition mention; confirm this refers to an organization, "
        "not just the event itself."
    ),
}


def organization_canonical_type_mismatch_display_message(item: dict[str, Any]) -> str:
    """Product copy for ``organization_canonical_type_mismatch`` review reasons."""
    message = item.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    return ORGANIZATION_CANONICAL_TYPE_MISMATCH_MESSAGE


def borderline_organization_boundary_display_message(item: dict[str, Any]) -> str:
    """Product copy for ``borderline_organization_boundary`` review reasons."""
    message = item.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()
    boundary = str(item.get("boundary") or "").strip()
    return _BOUNDARY_DISPLAY_MESSAGES.get(
        boundary,
        "Confirm this mention refers to an organization.",
    )
