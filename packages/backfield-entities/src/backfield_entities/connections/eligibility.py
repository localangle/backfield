"""Eligibility gates for automatic connection inference."""

from __future__ import annotations

from dataclasses import dataclass

from backfield_entities.ingest.db_output_settings import DbOutputCanonicalSettings


@dataclass(frozen=True)
class AutoConnectionsEligibility:
    enabled: bool
    eligible: bool
    reason: str


def evaluate_auto_connections_eligibility(
    settings: DbOutputCanonicalSettings,
) -> AutoConnectionsEligibility:
    if not settings.auto_connections_enabled:
        return AutoConnectionsEligibility(
            enabled=False,
            eligible=False,
            reason="disabled",
        )
    if not settings.stylebook_matching_enabled:
        return AutoConnectionsEligibility(
            enabled=True,
            eligible=False,
            reason="stylebook_matching_off",
        )
    if settings.canonicalization_mode != "ai_assisted":
        return AutoConnectionsEligibility(
            enabled=True,
            eligible=False,
            reason="canonicalization_not_ai_assisted",
        )
    if not settings.auto_apply_canonicalization:
        return AutoConnectionsEligibility(
            enabled=True,
            eligible=False,
            reason="auto_apply_off",
        )
    return AutoConnectionsEligibility(enabled=True, eligible=True, reason="eligible")
