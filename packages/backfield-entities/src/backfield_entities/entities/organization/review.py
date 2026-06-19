"""Organization extract boundary review routing for borderline cousin mentions."""

from __future__ import annotations

from typing import Any

from backfield_entities.canonical.plan_types import (
    CanonicalPersistDecision,
    CanonicalPersistPlan,
)

ORGANIZATION_BOUNDARY_VALUES: tuple[str, ...] = (
    "borderline_brand_platform",
    "borderline_work_title",
    "borderline_place_business",
    "borderline_event_competition",
)

BORDERLINE_ORGANIZATION_BOUNDARY_CODE = "borderline_organization_boundary"

_BOUNDARY_SHORT_BY_VALUE: dict[str, str] = {
    "borderline_brand_platform": "brand_platform",
    "borderline_work_title": "work_title",
    "borderline_place_business": "place_business",
    "borderline_event_competition": "event_competition",
}

_BOUNDARY_VALUE_BY_SHORT: dict[str, str] = {
    short: value for value, short in _BOUNDARY_SHORT_BY_VALUE.items()
}

DEFER_ONLY_ORGANIZATION_BOUNDARIES: frozenset[str] = frozenset(
    {
        "borderline_brand_platform",
        "borderline_event_competition",
    }
)


def normalize_organization_boundary(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    s = value.strip().lower()
    return s if s in ORGANIZATION_BOUNDARY_VALUES else None


def parse_organization_boundary_from_entry(entry: dict[str, Any]) -> str | None:
    return normalize_organization_boundary(entry.get("organization_boundary"))


def organization_boundary_short_name(boundary: str) -> str | None:
    return _BOUNDARY_SHORT_BY_VALUE.get(boundary)


def entry_has_borderline_organization_boundary(entry: dict[str, Any]) -> bool:
    return parse_organization_boundary_from_entry(entry) is not None


def organization_boundary_recommends_defer_only(boundary: str | None) -> bool:
    """Brand/platform and event/competition mentions should defer canonical linking."""
    if not isinstance(boundary, str):
        return False
    return boundary.strip().lower() in DEFER_ONLY_ORGANIZATION_BOUNDARIES


def parse_organization_boundary_from_review_reasons(
    reasons: Any,
) -> str | None:
    """Read full boundary value from stored review reason dicts."""
    if not isinstance(reasons, list):
        return None
    for item in reasons:
        if not isinstance(item, dict):
            continue
        if str(item.get("code") or "") != BORDERLINE_ORGANIZATION_BOUNDARY_CODE:
            continue
        short = str(item.get("boundary") or "").strip()
        return _BOUNDARY_VALUE_BY_SHORT.get(short)
    return None


def organization_review_recommends_defer_only(reasons: Any) -> bool:
    boundary = parse_organization_boundary_from_review_reasons(reasons)
    return organization_boundary_recommends_defer_only(boundary)


def boundary_review_data_json(boundary: str) -> dict[str, str]:
    return {"organization_boundary": boundary}


def boundary_reason_dict(*, boundary: str) -> dict[str, str]:
    short = organization_boundary_short_name(boundary)
    if short is None:
        raise ValueError(f"unknown organization boundary: {boundary!r}")
    return {"code": BORDERLINE_ORGANIZATION_BOUNDARY_CODE, "boundary": short}


def plan_with_boundary_defer_override(
    plan: CanonicalPersistPlan,
    *,
    boundary: str,
) -> CanonicalPersistPlan:
    """Force pending review for borderline cousin mentions; suggest defer only."""
    reasons: list[dict[str, Any]] = [
        boundary_reason_dict(boundary=boundary),
        {
            "code": "canonical_suggestion",
            "source": "rules_plan",
            "suggested_action": "defer",
        },
    ]
    for item in plan.resolution_reasons:
        if not isinstance(item, dict):
            continue
        code = str(item.get("code") or "")
        if code in {BORDERLINE_ORGANIZATION_BOUNDARY_CODE, "canonical_suggestion"}:
            continue
        reasons.append(dict(item))
    return CanonicalPersistPlan(
        decision=CanonicalPersistDecision.DEFER,
        existing_canonical_id=None,
        resolution_reasons=tuple(reasons),
    )
