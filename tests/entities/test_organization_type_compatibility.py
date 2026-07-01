"""Tests for organization_type editorial compatibility when linking canonicals."""

from __future__ import annotations

from backfield_entities.entities.organization.types import organization_types_are_link_compatible


def test_organization_types_are_link_compatible_for_business_labels() -> None:
    assert organization_types_are_link_compatible("local_business", "company")
    assert organization_types_are_link_compatible("company", "local_business")


def test_organization_types_are_not_link_compatible_across_roles() -> None:
    assert not organization_types_are_link_compatible("sports_team", "government")
    assert not organization_types_are_link_compatible("school_district", "public_services")
