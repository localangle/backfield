"""Tests for deterministic PlaceExtract components builder."""

from agate_nodes.place_extract.article_context import extract_article_context
from agate_nodes.place_extract.components_build import build_components


def test_city_state_from_location_string() -> None:
    ctx = extract_article_context("News from Chicago, IL today.")
    components = build_components("Chicago, IL", "city", ctx)
    assert components["city"] == "Chicago"
    assert components["state"] == {"name": "Illinois", "abbr": "IL"}
    assert components["county"] == ""


def test_neighborhood_in_string() -> None:
    ctx = extract_article_context("Crime in River North, Chicago, IL.")
    components = build_components("River North, Chicago, IL", "neighborhood", ctx)
    assert components["neighborhood"] == "River North"
    assert components["city"] == "Chicago"
    assert components["county"] == ""


def test_county_only_when_in_string() -> None:
    ctx = extract_article_context("Meeting in Cook County, IL.")
    components = build_components("Cook County, IL", "county", ctx)
    assert components["county"] == "Cook County"
    assert components["state"] == {"name": "Illinois", "abbr": "IL"}


def test_intersection_without_address_number() -> None:
    ctx = extract_article_context("Crash at I-290 and Pulaski Road, Chicago, IL.")
    components = build_components(
        "I-290 and Pulaski Road, Chicago, IL",
        "intersection_highway",
        ctx,
    )
    assert components["address"] == ""
    assert components["city"] == "Chicago"


def test_span_endpoints() -> None:
    ctx = extract_article_context("Closure on I-35 between Pine City and Hinckley, MN.")
    components = build_components(
        "I-35 between Pine City and Hinckley, MN",
        "span",
        ctx,
    )
    assert components["span"]["start"]["location"].startswith("Pine City")
    assert components["span"]["end"]["location"].startswith("Hinckley")


def test_state_inferred_from_article_context() -> None:
    article = "SPRINGFIELD — Lawmakers met Tuesday in Springfield."
    ctx = extract_article_context(article)
    components = build_components("Springfield", "city", ctx)
    assert components["city"] == "Springfield"
    assert components["state"]["abbr"] in {"", "IL"}


def test_place_with_embedded_street_address() -> None:
    ctx = extract_article_context("A festival was held at Humboldt Park in Chicago.")
    components = build_components(
        "Humboldt Park, 2800 W. Division St., Chicago, IL",
        "place",
        ctx,
    )
    assert components["place"]["name"] == "Humboldt Park"
    assert components["place"]["natural"] is True
    assert components["place"]["addressable"] is True
    assert "2800" in components["address"]
    assert "Division" in components["address"]
    assert components["city"] == "Chicago"


def test_block_address_normalizes_journalistic_phrasing() -> None:
    ctx = extract_article_context(
        "Shooting on the 6500 block of South Hermitage Avenue in Chicago."
    )
    location = "6500 block of South Hermitage Avenue, Chicago, IL"
    components = build_components(location, "address", ctx)
    assert components["address"] == "6500 S Hermitage Ave"
    assert components["city"] == "Chicago"
    assert components["state"] == {"name": "Illinois", "abbr": "IL"}


def test_foreign_country_prevents_domestic_context_inference() -> None:
    ctx = extract_article_context("The report was filed in Chicago, IL.")
    components = build_components("Paris, France", "city", ctx)
    assert components["city"] == "Paris"
    assert components["state"] == {"name": "", "abbr": ""}
    assert components["country"] == {"name": "France", "abbr": "FR"}


def test_country_type_prefers_iso_code_over_ambiguous_subdivision_code() -> None:
    ctx = extract_article_context("The report was filed in Chicago, IL.")
    components = build_components("IN", "country", ctx)
    assert components["state"] == {"name": "", "abbr": ""}
    assert components["country"] == {"name": "India", "abbr": "IN"}


def test_foreign_subdivision_and_postal_code_are_parsed_from_right() -> None:
    ctx = extract_article_context("The report was filed in Chicago, IL.")
    components = build_components("Toronto, ON M5V 3A8, Canada", "city", ctx)
    assert components["city"] == "Toronto"
    assert components["state"] == {"name": "Ontario", "abbr": "ON"}
    assert components["country"] == {"name": "Canada", "abbr": "CA"}
    assert components["postal_code"] == "M5V 3A8"


def test_domestic_zip_tail_is_removed_before_subdivision_parsing() -> None:
    ctx = extract_article_context("")
    components = build_components("123 Main St, Springfield, IL 62701", "address", ctx)
    assert components["address"] == "123 Main St"
    assert components["city"] == "Springfield"
    assert components["state"] == {"name": "Illinois", "abbr": "IL"}
    assert components["country"] == {"name": "United States", "abbr": "US"}
    assert components["postal_code"] == "62701"


def test_bare_subdivision_and_territory_use_normalized_iso_data() -> None:
    ctx = extract_article_context("")
    subdivision = build_components("Ontario", "state", ctx)
    territory = build_components("San Juan, PR 00901", "city", ctx)
    assert subdivision["state"] == {"name": "Ontario", "abbr": "ON"}
    assert subdivision["country"] == {"name": "Canada", "abbr": "CA"}
    assert territory["city"] == "San Juan"
    assert territory["state"] == {"name": "Puerto Rico", "abbr": "PR"}
    assert territory["country"] == {"name": "United States", "abbr": "US"}
    assert territory["postal_code"] == "00901"


def test_foreign_postal_tail_without_subdivision() -> None:
    ctx = extract_article_context("News from Boston, MA.")
    components = build_components("10 Downing St, London SW1A 2AA, United Kingdom", "address", ctx)
    assert components["address"] == "10 Downing St"
    assert components["city"] == "London"
    assert components["state"] == {"name": "", "abbr": ""}
    assert components["country"] == {"name": "United Kingdom", "abbr": "GB"}
    assert components["postal_code"] == "SW1A 2AA"

