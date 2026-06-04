"""Tests for location candidate review display copy."""

from backfield_stylebook.entities.location.review_display import deferred_policy_display_message


def test_deferred_policy_needs_review_bucket() -> None:
    msg = deferred_policy_display_message(
        {
            "code": "deferred_policy",
            "places_bucket": "needs_review",
            "substrate_status": "resolved",
            "location_type": "place",
        }
    )
    assert msg == "Flagged during geocoding — confirm before linking in Stylebook"


def test_deferred_policy_geocode_qa_code() -> None:
    msg = deferred_policy_display_message(
        {
            "code": "deferred_policy",
            "places_bucket": "needs_review",
            "geocode_qa_code": "geocode_city_level_fallback",
            "location_type": "place",
        }
    )
    assert msg == "Map pin may be too broad — confirm the exact location"


def test_deferred_policy_prefers_explicit_message() -> None:
    msg = deferred_policy_display_message(
        {
            "code": "deferred_policy",
            "message": "Custom editor-facing note",
            "places_bucket": "needs_review",
        }
    )
    assert msg == "Custom editor-facing note"
