"""Unit tests for person/organization/location obvious link mismatch predicates."""

from __future__ import annotations

from backfield_entities.entities.location.link_identity import (
    location_link_is_obvious_mismatch,
    location_names_share_obvious_identity,
)
from backfield_entities.entities.organization.name_mismatch import (
    organization_link_is_obvious_mismatch,
    organization_names_share_significant_token,
)
from backfield_entities.entities.person.name_mismatch import person_link_is_obvious_mismatch


def test_person_mismatch_clear_positive() -> None:
    assert person_link_is_obvious_mismatch(
        substrate_name="John Smith",
        canonical_label="Jane Doe",
    )


def test_person_mismatch_same_name_rescued() -> None:
    assert not person_link_is_obvious_mismatch(
        substrate_name="John Smith",
        canonical_label="John Smith",
    )


def test_person_mismatch_surname_only_rescued() -> None:
    assert not person_link_is_obvious_mismatch(
        substrate_name="Smith",
        canonical_label="Jane Smith",
    )


def test_person_mismatch_single_token_excluded() -> None:
    assert not person_link_is_obvious_mismatch(
        substrate_name="Bob",
        canonical_label="Robert Smith",
    )


def test_person_mismatch_editorial_alias_rescued() -> None:
    assert not person_link_is_obvious_mismatch(
        substrate_name="Mark Zuckerberg",
        canonical_label="Meta Platforms",
        editorial_alias_keys=frozenset({"mark zuckerberg"}),
    )


def test_organization_mismatch_clear_positive() -> None:
    assert organization_link_is_obvious_mismatch(
        substrate_name="Acme Corporation",
        canonical_label="Globex Industries",
    )


def test_organization_mismatch_acronym_rescued() -> None:
    assert not organization_link_is_obvious_mismatch(
        substrate_name="CPS",
        canonical_label="Chicago Public Schools",
    )


def test_organization_mismatch_shared_token_rescued() -> None:
    assert organization_names_share_significant_token(
        "Chicago Teachers Union",
        "Chicago Public Schools",
    )
    assert not organization_link_is_obvious_mismatch(
        substrate_name="Chicago Teachers Union",
        canonical_label="Chicago Public Schools",
    )


def test_organization_mismatch_editorial_alias_rescued() -> None:
    assert not organization_link_is_obvious_mismatch(
        substrate_name="Facebook",
        canonical_label="Meta Platforms",
        editorial_alias_keys=frozenset({"facebook"}),
    )


def test_organization_mismatch_equal_normalized_rescued() -> None:
    assert not organization_link_is_obvious_mismatch(
        substrate_name="Chicago Police Department",
        canonical_label="Chicago Police Department",
    )


def test_location_mismatch_incompatible_streets() -> None:
    assert location_link_is_obvious_mismatch(
        substrate_name="62nd Street, Chicago, IL",
        substrate_normalized_name="62nd street, chicago, il",
        substrate_location_type="street_road",
        components={"city": "Chicago"},
        formatted_address=None,
        geometry_type="LineString",
        canonical_label="Chicago Avenue, Near North Side, Chicago, IL",
        canonical_location_type="street_road",
    )


def test_location_mismatch_same_street_neighborhood_tail_not_flagged() -> None:
    assert not location_link_is_obvious_mismatch(
        substrate_name="Michigan Avenue, Loop, Chicago, IL",
        substrate_normalized_name="michigan avenue, loop, chicago, il",
        substrate_location_type="street_road",
        components={"city": "Chicago"},
        formatted_address=None,
        geometry_type="LineString",
        canonical_label="Michigan Avenue, Magnificent Mile, Chicago, IL",
        canonical_location_type="street_road",
    )


def test_location_mismatch_poi_vs_region() -> None:
    assert location_link_is_obvious_mismatch(
        substrate_name="Kingdom Home, Eastern Uganda, Uganda",
        substrate_normalized_name="kingdom home, eastern uganda, uganda",
        substrate_location_type="place",
        components={"place": {"name": "Kingdom Home"}},
        formatted_address=None,
        geometry_type="Point",
        canonical_label="Eastern Uganda",
        canonical_location_type="region_state",
    )


def test_location_mismatch_white_house_subfeature_not_flagged() -> None:
    assert not location_link_is_obvious_mismatch(
        substrate_name="White House driveway, Washington, DC",
        substrate_normalized_name="white house driveway, washington, dc",
        substrate_location_type="place",
        components={"place": {"name": "White House driveway"}},
        formatted_address=None,
        geometry_type="Point",
        canonical_label="White House, Washington, DC",
        canonical_location_type="place",
    )


def test_location_mismatch_downtown_neighborhood_region_city_not_flagged() -> None:
    assert location_names_share_obvious_identity(
        "Downtown, Chicago, IL",
        "Downtown, Chicago, IL",
    )
    assert not location_link_is_obvious_mismatch(
        substrate_name="Downtown, Chicago, IL",
        substrate_normalized_name="downtown, chicago, il",
        substrate_location_type="neighborhood",
        components={"city": "Chicago"},
        formatted_address=None,
        geometry_type="Polygon",
        canonical_label="Downtown, Chicago, IL",
        canonical_location_type="region_city",
    )


def test_location_mismatch_loop_alias_not_flagged() -> None:
    assert not location_link_is_obvious_mismatch(
        substrate_name="The Loop, Chicago, IL",
        substrate_normalized_name="the loop, chicago, il",
        substrate_location_type="region_city",
        components={"city": "Chicago"},
        formatted_address=None,
        geometry_type="Polygon",
        canonical_label="Loop, Chicago, IL",
        canonical_location_type="neighborhood",
    )


def test_location_mismatch_case_only_difference_not_flagged() -> None:
    assert not location_link_is_obvious_mismatch(
        substrate_name="Ymca, West Garfield Park, Chicago, IL",
        substrate_normalized_name="ymca, west garfield park, chicago, il",
        substrate_location_type="place",
        components={"place": {"name": "Ymca"}},
        formatted_address=None,
        geometry_type="Point",
        canonical_label="YMCA, West Garfield Park, Chicago, IL",
        canonical_location_type="place",
    )
