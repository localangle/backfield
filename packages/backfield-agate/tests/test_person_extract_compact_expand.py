"""Tests for compact PersonExtract enum code maps and row expansion."""

from __future__ import annotations

import pytest
from agate_nodes.person_extract.compact_expand import (
    PERSON_NATURE_CODES,
    PERSON_NATURE_FROM_CODE,
    PERSON_TYPE_CODES,
    PERSON_TYPE_FROM_CODE,
    expand_compact_person_row,
    expand_person_nature,
    expand_person_type,
)
from agate_nodes.person_extract.llm_person_parse import person_from_llm_entry
from backfield_entities.entities.person.types import PERSON_NATURE_VALUES, PERSON_TYPE_VALUES


def test_person_type_codes_cover_all_values() -> None:
    assert set(PERSON_TYPE_CODES.keys()) == set(PERSON_TYPE_VALUES)
    assert len(PERSON_TYPE_FROM_CODE) == len(PERSON_TYPE_CODES)
    assert set(PERSON_TYPE_FROM_CODE.values()) == set(PERSON_TYPE_CODES.keys())


def test_person_nature_codes_cover_all_values() -> None:
    assert set(PERSON_NATURE_CODES.keys()) == set(PERSON_NATURE_VALUES)
    assert len(PERSON_NATURE_FROM_CODE) == len(PERSON_NATURE_CODES)
    assert set(PERSON_NATURE_FROM_CODE.values()) == set(PERSON_NATURE_CODES.keys())


def test_expand_person_type_round_trips_codes() -> None:
    assert expand_person_type("eo") == "elected_official"
    assert expand_person_type("ath") == "athlete"


def test_expand_person_type_accepts_full_slug() -> None:
    assert expand_person_type("elected_official") == "elected_official"


def test_expand_person_nature_round_trips_codes() -> None:
    assert expand_person_nature("of") == "official"
    assert expand_person_nature("su") == "subject"


def test_expand_compact_person_row_builds_full_dict() -> None:
    entry = expand_compact_person_row(
        [
            "Jane Doe",
            "Mayor",
            "City of Chicago",
            1,
            "eo",
            "Announced policy",
            "of",
            [["Mayor Jane Doe announced policy.", 0]],
            {"st": ["so"]},
        ]
    )
    assert entry["name"] == "Jane Doe"
    assert entry["public_figure"] is True
    assert entry["type"] == "elected_official"
    assert entry["nature"] == "official"
    assert entry["nature_secondary_tags"] == ["source"]
    assert entry["mentions"] == [{"text": "Mayor Jane Doe announced policy.", "quote": False}]


def test_expand_compact_person_row_without_extras() -> None:
    entry = expand_compact_person_row(
        [
            "Pat Lee",
            "",
            "",
            0,
            "un",
            "Mentioned briefly",
            "ot",
            [["Pat Lee was there.", 0]],
        ]
    )
    assert entry["type"] == "unknown"
    assert "nature_secondary_tags" not in entry


def test_expand_compact_person_row_review_extras() -> None:
    entry = expand_compact_person_row(
        [
            "Buddy",
            "",
            "",
            0,
            "oth",
            "Family dog",
            "ot",
            [["The family dog Buddy was unharmed.", 0]],
            {
                "review": {
                    "handling": "auto_defer",
                    "reason_code": "animal",
                    "message": "Identified as an animal",
                }
            },
        ]
    )
    assert entry["review_handling"] == "auto_defer"
    assert entry["review_reason_code"] == "animal"


def test_expand_compact_person_row_surname_inferred_flag() -> None:
    entry = expand_compact_person_row(
        [
            "Peter Wirtz",
            "",
            "",
            0,
            "oth",
            "Brother of Rocky Wirtz",
            "pa",
            [["Rocky Wirtz's brother, Peter, spoke briefly.", 0]],
            {"si": 1},
        ]
    )
    assert entry["surname_inferred_from_relative"] is True


def test_expand_compact_person_row_raises_on_non_list() -> None:
    with pytest.raises(ValueError, match="array"):
        expand_compact_person_row({"name": "Jane Doe"})


def test_expand_compact_person_row_raises_on_empty_name() -> None:
    with pytest.raises(ValueError, match="name"):
        expand_compact_person_row(["", "", "", 0, "un", "", "ot", [["text", 0]]])


def test_compact_person_parity_matches_full_dict() -> None:
    full_entry = {
        "name": "Jane Doe",
        "title": "Mayor",
        "affiliation": "City of Chicago",
        "public_figure": True,
        "type": "elected_official",
        "role_in_story": "Announced policy",
        "nature": "official",
        "nature_secondary_tags": ["source"],
        "mentions": [{"text": "Mayor Jane Doe announced policy.", "quote": False}],
    }
    compact_row = [
        "Jane Doe",
        "Mayor",
        "City of Chicago",
        1,
        "eo",
        "Announced policy",
        "of",
        [["Mayor Jane Doe announced policy.", 0]],
        {"st": ["so"]},
    ]
    full_person = person_from_llm_entry(full_entry)
    compact_person = person_from_llm_entry(expand_compact_person_row(compact_row))
    assert full_person.model_dump() == compact_person.model_dump()


def test_compact_person_review_parity() -> None:
    full_entry = {
        "name": "Buddy",
        "title": "",
        "affiliation": "",
        "public_figure": False,
        "type": "other",
        "role_in_story": "Family dog",
        "nature": "other",
        "review_handling": "auto_defer",
        "review_reason_code": "animal",
        "review_message": "Identified as an animal",
        "mentions": [{"text": "The family dog Buddy was unharmed.", "quote": False}],
    }
    compact_row = [
        "Buddy",
        "",
        "",
        0,
        "oth",
        "Family dog",
        "ot",
        [["The family dog Buddy was unharmed.", 0]],
        {
            "review": {
                "handling": "auto_defer",
                "reason_code": "animal",
                "message": "Identified as an animal",
            }
        },
    ]
    full_person = person_from_llm_entry(full_entry)
    compact_person = person_from_llm_entry(expand_compact_person_row(compact_row))
    assert full_person.model_dump() == compact_person.model_dump()
