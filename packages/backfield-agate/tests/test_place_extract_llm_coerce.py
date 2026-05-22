"""PlaceExtract LLM response coercion and per-entry parsing."""

from agate_nodes.place_extract.llm_location_coerce import coerce_llm_location_entry
from agate_nodes.place_extract.llm_location_parse import place_from_llm_location_entry


def test_coerce_missing_components_defaults_empty_dict() -> None:
    raw = {
        "location": "Springfield, IL",
        "type": "city",
        "original_text": "Springfield leaders met Tuesday.",
        "description": "State capital city referenced in the lede.",
    }
    out = coerce_llm_location_entry(raw)
    assert out["components"] == {}


def test_coerce_nested_location_dict_hoists_components() -> None:
    raw = {
        "location": {
            "full": "Ohio",
            "type": "state",
            "components": {"state": {"name": "Ohio", "abbr": "OH"}},
        },
        "original_text": "Ohio lawmakers advanced the bill.",
        "description": "U.S. state where the legislature acted.",
    }
    out = coerce_llm_location_entry(raw)
    assert out["location"] == "Ohio"
    assert out["type"] == "state"
    assert out["components"]["state"]["abbr"] == "OH"


def test_place_from_llm_entry_without_components_succeeds() -> None:
    place = place_from_llm_location_entry(
        {
            "location": "Chicago, IL",
            "type": "city",
            "original_text": "In Chicago, officials announced reforms.",
            "description": "Major city where officials spoke.",
        }
    )
    assert place.location.full == "Chicago, IL"
    assert place.location.type == "city"
    assert place.location.components.city == ""


def test_place_from_llm_entry_skips_only_when_all_invalid() -> None:
    """One bad entry should not block parsing valid siblings (caller skips in loop)."""
    good = place_from_llm_location_entry(
        {
            "location": "Ohio",
            "type": "state",
            "original_text": "Ohio",
            "description": "State",
            "components": {},
        }
    )
    assert good.location.full == "Ohio"
