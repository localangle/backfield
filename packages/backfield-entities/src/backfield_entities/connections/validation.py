"""Validation gates for automatic connection candidates."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_entities.connections.taxonomy import (
    AUTO_CONNECTION_MIN_CONFIDENCE,
    allowed_location_types_for_auto_nature,
    auto_link_natures_for_pair,
    is_auto_link_endpoint_pair,
    person_location_forbidden_location_types,
)


@dataclass(frozen=True)
class AutoConnectionValidationResult:
    ok: bool
    skip_reason: str | None = None


def _normalize_location_type(location_type: str | None) -> str:
    return (location_type or "").strip().lower()


def validate_auto_connection_candidate(
    *,
    from_entity_type: str,
    to_entity_type: str,
    nature: str,
    confidence: float,
    quote: str,
    location_type: str | None = None,
) -> AutoConnectionValidationResult:
    """Validate a high-confidence auto-connection candidate before persistence."""
    from_type = from_entity_type.strip().lower()
    to_type = to_entity_type.strip().lower()
    nature_key = nature.strip().lower()
    quote_text = quote.strip()

    if not is_auto_link_endpoint_pair(from_type, to_type):
        return AutoConnectionValidationResult(
            ok=False,
            skip_reason="endpoint_pair_not_allowed",
        )

    allowed_natures = auto_link_natures_for_pair(from_type, to_type)
    if nature_key not in allowed_natures:
        return AutoConnectionValidationResult(
            ok=False,
            skip_reason="nature_not_allowed",
        )

    if confidence < AUTO_CONNECTION_MIN_CONFIDENCE:
        return AutoConnectionValidationResult(
            ok=False,
            skip_reason="confidence_below_threshold",
        )

    if not quote_text:
        return AutoConnectionValidationResult(
            ok=False,
            skip_reason="missing_quote",
        )

    if to_type == "location":
        lt = _normalize_location_type(location_type)
        if not lt:
            return AutoConnectionValidationResult(
                ok=False,
                skip_reason="missing_location_type",
            )

        if from_type == "person" and lt in person_location_forbidden_location_types():
            return AutoConnectionValidationResult(
                ok=False,
                skip_reason="person_location_address_forbidden",
            )

        allowed_types = allowed_location_types_for_auto_nature(nature_key)
        if allowed_types is not None and lt not in allowed_types:
            return AutoConnectionValidationResult(
                ok=False,
                skip_reason="location_granularity_not_allowed",
            )

    return AutoConnectionValidationResult(ok=True)
