"""Organization boundary review routing tests."""

from __future__ import annotations

from backfield_entities.canonical.plan_types import CanonicalPersistDecision, CanonicalPersistPlan
from backfield_entities.entities.organization.review import (
    BORDERLINE_ORGANIZATION_BOUNDARY_CODE,
    boundary_reason_dict,
    normalize_organization_boundary,
    parse_organization_boundary_from_entry,
    plan_with_boundary_defer_override,
)
from backfield_entities.entities.organization.review_display import (
    borderline_organization_boundary_display_message,
)


def test_normalize_organization_boundary_accepts_known_values() -> None:
    assert normalize_organization_boundary("borderline_work_title") == "borderline_work_title"
    assert (
        normalize_organization_boundary(" Borderline_Brand_Platform ")
        == "borderline_brand_platform"
    )


def test_normalize_organization_boundary_rejects_unknown() -> None:
    assert normalize_organization_boundary("borderline_other") is None
    assert normalize_organization_boundary(None) is None


def test_parse_organization_boundary_from_entry() -> None:
    entry = {"organization_boundary": "borderline_event_competition", "name": "Lollapalooza"}
    assert parse_organization_boundary_from_entry(entry) == "borderline_event_competition"


def test_plan_with_boundary_defer_override_suggests_defer_only() -> None:
    prior = CanonicalPersistPlan(
        decision=CanonicalPersistDecision.LINK_EXISTING,
        existing_canonical_id="canon-twitter",
        resolution_reasons=({"code": "linked_exact_identity", "canonical_id": "canon-twitter"},),
    )
    plan = plan_with_boundary_defer_override(
        prior,
        boundary="borderline_brand_platform",
    )
    assert plan.decision == CanonicalPersistDecision.DEFER
    assert plan.existing_canonical_id is None
    codes = [str(r.get("code") or "") for r in plan.resolution_reasons if isinstance(r, dict)]
    assert BORDERLINE_ORGANIZATION_BOUNDARY_CODE in codes
    assert "canonical_suggestion" in codes
    suggestion = next(
        r for r in plan.resolution_reasons if r.get("code") == "canonical_suggestion"
    )
    assert suggestion.get("suggested_action") == "defer"
    assert "stylebook_organization_canonical_id" not in suggestion


def test_plan_with_boundary_defer_override_replaces_materialize_new_suggestion() -> None:
    prior = CanonicalPersistPlan(
        decision=CanonicalPersistDecision.MATERIALIZE_NEW,
        resolution_reasons=({"code": "no_canonical_match",},),
    )
    plan = plan_with_boundary_defer_override(
        prior,
        boundary="borderline_work_title",
    )
    suggestion = next(
        r for r in plan.resolution_reasons if r.get("code") == "canonical_suggestion"
    )
    assert suggestion.get("suggested_action") == "defer"


def test_boundary_reason_dict_short_name() -> None:
    assert boundary_reason_dict(boundary="borderline_work_title") == {
        "code": BORDERLINE_ORGANIZATION_BOUNDARY_CODE,
        "boundary": "work_title",
    }


def test_borderline_organization_boundary_display_messages() -> None:
    assert (
        borderline_organization_boundary_display_message({"boundary": "brand_platform"})
        == "Brand or platform mention; confirm this refers to an organization, "
        "not just a service, product, or brand."
    )
    assert (
        borderline_organization_boundary_display_message({"boundary": "work_title"})
        == "Work or title mention; confirm this refers to an organization, "
        "not a creative work or publication title."
    )
