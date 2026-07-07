"""Tests for compact PlaceExtract array row parsing."""

import pytest
from agate_nodes.place_extract.compact_array_parse import (
    is_compact_array_entry,
    parse_compact_locations,
    row_to_entry,
)


def test_row_to_entry_expands_codes() -> None:
    entry = row_to_entry(
        [
            "Grant Park, Chicago, IL",
            "pl",
            "p",
            "",
            "Festival venue.",
            "",
            "Grant Park",
        ]
    )
    assert entry["location"] == "Grant Park, Chicago, IL"
    assert entry["type"] == "place"
    assert entry["nature"] == "primary"
    assert entry["address_place_kind"] == ""
    assert entry["evidence_anchor"] == "Grant Park"


def test_row_to_entry_pads_short_rows() -> None:
    entry = row_to_entry(["Chicago, IL", "ci", "c"])
    assert entry["location"] == "Chicago, IL"
    assert entry["type"] == "city"
    assert entry["description"] == ""
    assert entry["geocode_hints"] == ""
    assert entry["evidence_anchor"] == ""


def test_parse_compact_locations_accepts_object_rows() -> None:
    rows = parse_compact_locations(
        {
            "locations": [
                {
                    "location": "Ohio",
                    "type": "st",
                    "nature": "c",
                    "description": "State context.",
                    "geocode_hints": "",
                }
            ]
        }
    )
    assert rows[0]["type"] == "state"
    assert rows[0]["nature"] == "context"


def test_parse_compact_locations_rejects_missing_locations() -> None:
    with pytest.raises(ValueError, match="locations array"):
        parse_compact_locations({})


def test_is_compact_array_entry() -> None:
    assert is_compact_array_entry(
        {
            "location": "Chicago, IL",
            "type": "city",
            "description": "City.",
            "geocode_hints": "",
            "nature": "context",
        }
    )
    assert not is_compact_array_entry(
        {
            "location": "Chicago, IL",
            "type": "city",
            "original_text": "In Chicago.",
            "description": "City.",
            "components": {},
        }
    )
