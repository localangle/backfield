"""Golden shape tests for compact PlaceExtract expansion."""

from __future__ import annotations

from typing import Any

from agate_nodes.place_extract.compact_expand import expand_compact_entry
from agate_nodes.place_extract.llm_location_parse import place_from_llm_location_entry


def _shape(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _shape(value[key]) for key in sorted(value.keys())}
    if isinstance(value, list):
        return [_shape(item) for item in value]
    return type(value).__name__


FULL_STYLE_ENTRY = {
    "location": "River North, Chicago, IL",
    "type": "neighborhood",
    "original_text": "Chicago police responded in River North overnight.",
    "description": "Neighborhood where the robbery occurred.",
    "geocode_hints": "",
    "nature": "primary",
    "nature_secondary_tags": [],
    "mentions": [{"text": "Chicago police responded in River North overnight."}],
    "components": {
        "place": {},
        "street_road": {},
        "span": {},
        "address": "",
        "neighborhood": "River North",
        "city": "Chicago",
        "county": "Cook County",
        "postal_code": "",
        "state": {"name": "Illinois", "abbr": "IL"},
        "country": {"name": "United States", "abbr": "US"},
    },
}

COMPACT_ROW = {
    "location": "River North, Chicago, IL",
    "type": "neighborhood",
    "nature": "primary",
    "address_place_kind": "",
    "description": "Neighborhood where the robbery occurred.",
    "geocode_hints": "",
    "evidence_anchor": "River North",
}

ARTICLE = "Chicago police responded in River North overnight."


def test_compact_expand_matches_full_shape() -> None:
    full_place = place_from_llm_location_entry(FULL_STYLE_ENTRY)
    compact_place = place_from_llm_location_entry(
        expand_compact_entry(ARTICLE, COMPACT_ROW),
    )
    assert _shape(full_place.model_dump()) == _shape(compact_place.model_dump())


def test_compact_expand_preserves_foreign_full_type_and_postal_components() -> None:
    place = place_from_llm_location_entry(
        expand_compact_entry(
            "The event occurred at 10 Downing St.",
            {
                "location": "10 Downing St, London SW1A 2AA, United Kingdom",
                "type": "address",
                "nature": "primary",
                "address_place_kind": "unknown",
                "description": "Event address.",
                "geocode_hints": "",
                "evidence_anchor": "10 Downing St",
            },
        )
    )
    dumped = place.model_dump()
    assert dumped["location"]["full"] == "10 Downing St, London SW1A 2AA, United Kingdom"
    assert dumped["location"]["type"] == "address"
    assert dumped["location"]["components"]["city"] == "London"
    assert dumped["location"]["components"]["state"] is None
    assert dumped["location"]["components"]["country"] == {
        "name": "United Kingdom",
        "abbr": "GB",
    }
    assert dumped["location"]["components"]["postal_code"] == "SW1A 2AA"


def test_compact_street_level_includes_address_place_kind() -> None:
    place = place_from_llm_location_entry(
        expand_compact_entry(
            "Crash on I-290 and Pulaski Road, Chicago, IL.",
            {
                "location": "I-290 and Pulaski Road, Chicago, IL",
                "type": "intersection_highway",
                "nature": "primary",
                "address_place_kind": "",
                "description": "Crash site.",
                "geocode_hints": "",
            },
        )
    )
    dumped = place.model_dump()
    assert dumped["address_place_kind"] == "private_residence"
    assert all(set(item.keys()) == {"text"} for item in dumped["mentions"])


def test_compact_expand_uses_evidence_anchor_for_normalized_location() -> None:
    article = (
        "Organizers said they wanted to honor LGBTQ+ leaders, including "
        "Ald. Jessie Fuentes (26th), who walked in the parade."
    )
    place = place_from_llm_location_entry(
        expand_compact_entry(
            article,
            {
                "location": "Ward 26, Chicago, IL",
                "type": "political_district",
                "nature": "context",
                "address_place_kind": "",
                "description": "Ward represented by an alderperson who walked in the parade.",
                "geocode_hints": "",
                "evidence_anchor": "Ald. Jessie Fuentes (26th)",
            },
        )
    )
    dumped = place.model_dump()
    assert dumped["location"]["full"] == "Ward 26, Chicago, IL"
    assert dumped["original_text"] == article
    assert dumped["mentions"] == [{"text": article}]


def test_compact_expand_leaves_evidence_empty_when_anchor_and_location_do_not_match() -> None:
    place = place_from_llm_location_entry(
        expand_compact_entry(
            "No matching evidence here.",
            {
                "location": "Ward 26, Chicago, IL",
                "type": "political_district",
                "nature": "context",
                "address_place_kind": "",
                "description": "Ward mention.",
                "geocode_hints": "",
                "evidence_anchor": "Ald. Jessie Fuentes (26th)",
            },
        )
    )
    dumped = place.model_dump()
    assert dumped["original_text"] == ""
    assert dumped["mentions"] == []
