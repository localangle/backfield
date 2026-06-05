"""Human-readable lines from substrate ``canonical_review_reasons_json`` for candidate lists."""

from __future__ import annotations

from typing import Any

from backfield_entities.entities.location.review_display import deferred_policy_display_message

_SKIP_LIST_DISPLAY_CODES: frozenset[str] = frozenset(
    {
        "canonical_suggestion",
        "review_note",
        "deferred_manual",
    }
)

_DEFAULT_CODE_MESSAGES: dict[str, str] = {
    "ambiguous_canonical_match": "Several Stylebook locations could match this place.",
    "ambiguous_person_canonical_match": "Several Stylebook people could match this person.",
    "ambiguous_organization_canonical_match": (
        "Several Stylebook organizations could match this organization."
    ),
    "organization_canonical_type_mismatch": (
        "Organization type does not match the recalled Stylebook entry."
    ),
    "child": "Identified as a child",
    "animal": "Identified as an animal",
    "stage_name_or_alias": "Stage name or alias — confirm full identity before linking",
    "first_name_only": "First name only — confirm full identity before linking",
    "private_place_or_residence": "Private place or residence",
    "road_span_not_canonicalized": "Road spans are not auto-canonicalized",
    "geocode_country_mismatch": (
        "Place extraction disagrees with the geocoded address on country — confirm before linking"
    ),
    "geocode_state_mismatch": (
        "Place extraction disagrees with the geocoded address on state or province — "
        "confirm before linking"
    ),
}


def parse_review_reason_items(
    raw: list[Any] | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        return [raw]
    return []


def _line_for_reason(item: dict[str, Any]) -> str | None:
    code = str(item.get("code") or "").strip()
    if not code or code in _SKIP_LIST_DISPLAY_CODES:
        return None

    message = item.get("message")
    if isinstance(message, str) and message.strip():
        return message.strip()

    if code == "canonical_adjudication":
        rationale = item.get("rationale")
        if isinstance(rationale, str) and rationale.strip():
            return rationale.strip()
        outcome = str(item.get("outcome") or "").strip()
        if outcome == "no_high_confidence_link":
            return "No confident Stylebook match for this mention."
        if outcome == "district_key_mismatch_coerced":
            return "District identity does not match the recalled Stylebook entry."
        if outcome == "link_existing":
            return "Ingest suggested linking to an existing Stylebook entry."
        return None

    if code in (
        "ambiguous_canonical_match",
        "ambiguous_person_canonical_match",
        "ambiguous_organization_canonical_match",
    ):
        ids = item.get("recall_canonical_ids")
        if isinstance(ids, list) and len(ids) > 0:
            if code == "ambiguous_canonical_match":
                noun = "locations"
            elif code == "ambiguous_person_canonical_match":
                noun = "people"
            else:
                noun = "organizations"
            return f"Several Stylebook {noun} could match ({len(ids)} recalled)."
        return _DEFAULT_CODE_MESSAGES.get(code)

    if code == "deferred_policy":
        return deferred_policy_display_message(item)

    return _DEFAULT_CODE_MESSAGES.get(code)


def format_candidate_review_lines(
    raw: list[Any] | dict[str, Any] | None,
) -> list[str]:
    """Ordered, de-duplicated display lines for Stylebook candidate queue rows."""
    lines: list[str] = []
    seen: set[str] = set()
    for item in parse_review_reason_items(raw):
        line = _line_for_reason(item)
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return lines


def first_candidate_review_line(
    raw: list[Any] | dict[str, Any] | None,
) -> str | None:
    lines = format_candidate_review_lines(raw)
    return lines[0] if lines else None
