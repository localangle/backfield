"""Unit tests for person/organization/location obvious link mismatch predicates."""

from __future__ import annotations

from backfield_entities.entities.location.link_identity import (
    location_link_is_obvious_mismatch,
    location_merge_pair_blocked,
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


def test_person_mismatch_same_surname_different_given_audit_exemplars() -> None:
    """P0 audit: Kam→Tre and Tiffany→Adrienne must not auto-link."""
    assert person_link_is_obvious_mismatch(
        substrate_name="Kam Jones",
        canonical_label="Tre Jones",
    )
    assert person_link_is_obvious_mismatch(
        substrate_name="Tiffany Davis",
        canonical_label="Adrienne E. Davis",
    )


def test_person_mismatch_prefix_nickname_rescued() -> None:
    assert not person_link_is_obvious_mismatch(
        substrate_name="Rob Smith",
        canonical_label="Robert Smith",
    )


def test_person_mismatch_dotted_initials_rescued() -> None:
    """CJ vs C.J. must not veto — punctuation-only given-name difference."""
    assert not person_link_is_obvious_mismatch(
        substrate_name="CJ Stroud",
        canonical_label="C.J. Stroud",
    )


def test_person_mismatch_non_prefix_nickname_rescued() -> None:
    """Tom is not a prefix of Thomas; nickname map must still allow the link."""
    assert not person_link_is_obvious_mismatch(
        substrate_name="Tom Dart",
        canonical_label="Thomas Dart",
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


def test_organization_mismatch_university_of_x_audit_exemplar() -> None:
    """P0 audit: University of Maryland must not link via shared 'university' token."""
    assert organization_link_is_obvious_mismatch(
        substrate_name="University of Maryland",
        canonical_label="University of Minnesota Duluth",
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


def test_location_mismatch_river_heads_audit_exemplar() -> None:
    """P0 audit: DuPage River must not link to Illinois River."""
    assert location_link_is_obvious_mismatch(
        substrate_name="DuPage River, Illinois",
        substrate_normalized_name="dupage river illinois",
        substrate_location_type="natural",
        components={"state": {"abbr": "IL"}, "country": {"abbr": "US"}},
        formatted_address=None,
        geometry_type=None,
        canonical_label="Illinois River, Illinois",
        canonical_location_type="natural",
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


def test_location_merge_blocked_venue_into_containing_city() -> None:
    assert location_merge_pair_blocked(
        source_label="Perman, Chicago, IL",
        source_location_type="place",
        target_label="Chicago, IL",
        target_location_type="city",
    )


def test_location_merge_blocked_is_symmetric_for_city_keeper_order() -> None:
    assert location_merge_pair_blocked(
        source_label="Chicago, IL",
        source_location_type="city",
        target_label="Fox32, Chicago, IL",
        target_location_type="place",
    )


def test_location_merge_allowed_same_type() -> None:
    assert not location_merge_pair_blocked(
        source_label="Chicago Shakespeare Theatre, Chicago, IL",
        source_location_type="place",
        target_label="Chicago Shakespeare Theater, Chicago, IL",
        target_location_type="place",
    )


def test_location_merge_allowed_same_label_cross_type() -> None:
    assert not location_merge_pair_blocked(
        source_label="Near North Side, Chicago, IL",
        source_location_type="place",
        target_label="Near North Side, Chicago, IL",
        target_location_type="neighborhood",
    )


def test_location_merge_allowed_missing_types() -> None:
    assert not location_merge_pair_blocked(
        source_label="Kentucky",
        source_location_type=None,
        target_label="Kentucky, US",
        target_location_type="state",
    )


def test_location_mismatch_subcircuit_vs_congressional_district_flagged() -> None:
    """A judicial subcircuit row must flag when linked to a congressional district canonical."""
    assert location_link_is_obvious_mismatch(
        substrate_name="Congressional District 13, Illinois, US",
        substrate_normalized_name="congressional district 13, illinois, us",
        substrate_location_type="political_district",
        components={"city": "13th subcircuit", "county": "Cook County"},
        formatted_address="13th subcircuit, Cook County, IL (region estimate)",
        geometry_type="Polygon",
        canonical_label="Congressional District 13, IL",
        canonical_location_type="political_district",
        # The bad UI relink itself wrote this editorial alias; it must not rescue the link.
        editorial_alias_keys=frozenset({"congressional district 13, illinois, us"}),
    )


def test_location_mismatch_political_district_linked_to_city_flagged() -> None:
    """Ward/district rows misnamed after their city must flag on a city canonical."""
    assert location_link_is_obvious_mismatch(
        substrate_name="Chicago, IL",
        substrate_normalized_name="chicago, il",
        substrate_location_type="political_district",
        components={"city": "Chicago", "state": {"abbr": "IL"}},
        formatted_address="ward (region estimate)",
        geometry_type="Polygon",
        canonical_label="Chicago, IL",
        canonical_location_type="city",
    )


def test_location_mismatch_same_kind_congressional_district_not_flagged() -> None:
    assert not location_link_is_obvious_mismatch(
        substrate_name="Illinois's 9th Congressional District, IL",
        substrate_normalized_name="illinois's 9th congressional district, il",
        substrate_location_type="political_district",
        components={"state": {"abbr": "IL"}},
        formatted_address="Illinois's 9th Congressional District (region estimate)",
        geometry_type="Polygon",
        canonical_label="Congressional District 9, IL",
        canonical_location_type="political_district",
    )


def test_location_merge_blocked_political_district_into_same_named_city() -> None:
    """Identity escape hatch must not merge a district canonical into its city."""
    assert location_merge_pair_blocked(
        source_label="Chicago, IL",
        source_location_type="political_district",
        target_label="Chicago, IL",
        target_location_type="city",
    )


def test_location_merge_blocked_conflicting_district_kinds() -> None:
    assert location_merge_pair_blocked(
        source_label="1st Judicial Subcircuit, IL",
        source_location_type="political_district",
        target_label="Congressional District 1, IL",
        target_location_type="political_district",
    )


def test_location_merge_allowed_same_kind_political_districts() -> None:
    assert not location_merge_pair_blocked(
        source_label="Congressional District 13, Illinois, US",
        source_location_type="political_district",
        target_label="Congressional District 13, IL",
        target_location_type="political_district",
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
