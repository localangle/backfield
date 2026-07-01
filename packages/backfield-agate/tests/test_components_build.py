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
