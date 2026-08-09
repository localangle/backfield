from stylebook_api.helpers.candidate_review_display import (
    first_candidate_review_line,
    format_candidate_review_lines,
)


def test_content_sanity_coerced_prefers_outcome_copy_over_link_rationale() -> None:
    raw = [
        {
            "code": "canonical_adjudication",
            "outcome": "content_sanity_coerced",
            "rationale": (
                "Substrate 'Wishbone, West Loop, Chicago, IL' is the same "
                "real-world restaurant entity as 'Wishbone, Chicago, IL'."
            ),
            "confidence": 0.98,
            "canonical_id": "6e28e10d-164d-4353-8a94-7c78285aeffc",
        }
    ]
    assert format_candidate_review_lines(raw) == [
        "A possible Stylebook match was blocked by a content check — "
        "confirm before linking or creating a new entry.",
    ]


def test_format_lines_skips_ambiguous_canonical_match() -> None:
    raw = [
        {
            "code": "ambiguous_canonical_match",
            "recall_canonical_ids": ["a"] * 19,
        },
        {
            "code": "canonical_adjudication",
            "rationale": "Not the same place as recalled entries.",
            "outcome": "no_high_confidence_link",
        },
    ]
    assert format_candidate_review_lines(raw) == [
        "Not the same place as recalled entries.",
    ]


def test_format_lines_skips_suggestion_and_note() -> None:
    raw = [
        {"code": "canonical_suggestion", "suggested_action": "link_existing"},
        {"code": "review_note", "note": "editor note"},
        {
            "code": "ambiguous_person_canonical_match",
            "recall_canonical_ids": ["a", "b"],
        },
        {
            "code": "canonical_adjudication",
            "rationale": "None of the candidates match Greg Abbott.",
            "outcome": "no_high_confidence_link",
        },
    ]
    assert format_candidate_review_lines(raw) == [
        "None of the candidates match Greg Abbott.",
    ]


def test_first_line_prefers_message_over_code_default() -> None:
    raw = [
        {
            "code": "private_place_or_residence",
            "message": "Private place or residence",
        }
    ]
    assert first_candidate_review_line(raw) == "Private place or residence"


def test_adjudication_outcome_without_rationale() -> None:
    raw = [{"code": "canonical_adjudication", "outcome": "no_high_confidence_link"}]
    assert format_candidate_review_lines(raw) == [
        "No confident Stylebook match for this mention.",
    ]


def test_organization_type_mismatch_message() -> None:
    raw = [
        {
            "code": "organization_canonical_type_mismatch",
            "canonical_id": "canon-1",
            "substrate_type": "sports_team",
            "canonical_type": "government",
        }
    ]
    assert format_candidate_review_lines(raw) == [
        "Could not find Stylebook entry with matching type.",
    ]


def test_borderline_organization_boundary_line() -> None:
    raw = [
        {
            "code": "borderline_organization_boundary",
            "boundary": "place_business",
        }
    ]
    assert format_candidate_review_lines(raw) == [
        "Business or venue mention; confirm this refers to people or operations, "
        "not just a location.",
    ]


def test_deferred_policy_needs_review_line() -> None:
    raw = [
        {
            "code": "deferred_policy",
            "places_bucket": "needs_review",
            "substrate_status": "resolved",
            "location_type": "place",
        }
    ]
    assert format_candidate_review_lines(raw) == [
        "Flagged during geocoding — confirm before linking in Stylebook",
    ]


def test_geocode_quality_warning_is_visible_beside_recommendation() -> None:
    raw = [
        {
            "code": "geocode_quality_warning",
            "message": "Flagged during geocoding — confirm before linking in Stylebook",
        },
        {
            "code": "canonical_suggestion",
            "suggested_action": "link_existing",
        },
    ]
    assert format_candidate_review_lines(raw) == [
        "Flagged during geocoding — confirm before linking in Stylebook",
    ]
