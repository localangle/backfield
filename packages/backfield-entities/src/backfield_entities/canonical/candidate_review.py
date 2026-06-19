"""Shared helpers for Stylebook candidate queue review JSON."""

from __future__ import annotations

from typing import Any

AI_RECOMMENDATION_REASON_CODES: frozenset[str] = frozenset(
    {"canonical_suggestion", "canonical_adjudication"}
)


def review_reason_items(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [dict(r) for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        return [dict(raw)]
    return []


def strip_ai_recommendations_from_review_reasons(raw: Any) -> list[dict[str, Any]]:
    """Remove AI link/create/defer suggestions while keeping ingest review context."""
    return [
        item
        for item in review_reason_items(raw)
        if str(item.get("code") or "") not in AI_RECOMMENDATION_REASON_CODES
    ]
