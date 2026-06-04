"""Human-readable review context for location canonical deferrals."""

from __future__ import annotations

from typing import Any

_GEOCODE_QA_MESSAGES: dict[str, str] = {
    "geocode_region_mismatch": "Map region does not match the place named in the story",
    "geocode_city_level_fallback": "Map pin may be too broad — confirm the exact location",
    "geocode_admin_level_mismatch": "Map result does not match this type of place",
    "geocode_country_mismatch": "Story country does not match the geocoded address — confirm before linking",
    "geocode_state_mismatch": "Story state or province does not match the geocoded address — confirm before linking",
}

_ADDRESS_LIKE_TYPES: frozenset[str] = frozenset(
    {
        "address",
        "intersection_highway",
        "intersection_road",
        "street_road",
    }
)


def deferred_policy_display_message(item: dict[str, Any]) -> str:
    """Product copy for ``deferred_policy`` rows in ``canonical_review_reasons_json``."""
    message = item.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()

    qa = str(item.get("geocode_qa_code") or "").strip()
    if qa in _GEOCODE_QA_MESSAGES:
        return _GEOCODE_QA_MESSAGES[qa]

    places_bucket = str(item.get("places_bucket") or "").strip().lower()
    if places_bucket == "needs_review":
        return "Flagged during geocoding — confirm before linking in Stylebook"

    substrate_status = str(item.get("substrate_status") or "").strip().lower()
    if substrate_status == "failed":
        return "Geocoding failed — link or create a Stylebook entry manually"
    if substrate_status == "needs_review":
        return "Geocoding needs review before linking in Stylebook"

    location_type = str(item.get("location_type") or "").strip().lower()
    if location_type == "span":
        return "Road spans are not auto-canonicalized"
    if location_type in _ADDRESS_LIKE_TYPES:
        return "Addresses are not auto-linked — confirm before linking in Stylebook"

    fuzzy_ids = item.get("fuzzy_recall_canonical_ids")
    if isinstance(fuzzy_ids, list) and len(fuzzy_ids) > 0:
        return "Similar Stylebook entries found — confirm link or create new"

    if item.get("fuzzy_best_score") is not None:
        return "No confident Stylebook match — link or create manually"

    return "Needs review before linking in Stylebook"
