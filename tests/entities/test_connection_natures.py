"""Tests for the preferred connection nature catalog."""

from __future__ import annotations

from backfield_entities.connections.natures import (
    PREFERRED_NATURES,
    auto_link_natures_for_pair,
    is_auto_link_endpoint_pair,
    nature_def,
    normalize_preferred_nature_slug,
    preferred_natures_for_pair,
    temporal_kind_for_nature,
)


def test_catalog_has_core_auto_natures() -> None:
    person_org = auto_link_natures_for_pair("person", "organization")
    assert "works_for" in person_org
    assert "plays_for" in person_org
    assert "holds_office_in" in auto_link_natures_for_pair("person", "location")
    assert "team_of" in auto_link_natures_for_pair("organization", "organization")
    assert "donated_to" not in person_org  # manual first


def test_manual_natures_listed_but_not_auto() -> None:
    all_po = preferred_natures_for_pair("person", "organization")
    assert "donated_to" in all_po
    assert "donated_to" not in auto_link_natures_for_pair("person", "organization")


def test_alias_normalization() -> None:
    assert normalize_preferred_nature_slug("works_at") == "works_for"
    assert normalize_preferred_nature_slug("represented_by") == "represents"
    assert normalize_preferred_nature_slug("plays_for") == "plays_for"


def test_temporal_kinds() -> None:
    assert temporal_kind_for_nature("born_in", "person", "location") == "static"
    assert temporal_kind_for_nature("leads", "person", "organization") == "dynamic"
    assert temporal_kind_for_nature("parent_of", "person", "person") == "static"
    assert temporal_kind_for_nature("parent_of", "organization", "organization") == "dynamic"


def test_org_person_endorsed_pair() -> None:
    assert is_auto_link_endpoint_pair("organization", "person")
    assert "endorsed" in auto_link_natures_for_pair("organization", "person")


def test_holds_office_in_def() -> None:
    row = nature_def("holds_office_in", "person", "location")
    assert row is not None
    assert row.auto_allowed
    assert row.location_types is not None
    assert "city" in row.location_types


def test_no_duplicate_bindings() -> None:
    keys = {(n.slug, n.from_type, n.to_type) for n in PREFERRED_NATURES}
    assert len(keys) == len(PREFERRED_NATURES)
