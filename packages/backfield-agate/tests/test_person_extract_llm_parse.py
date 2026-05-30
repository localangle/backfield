"""PersonExtract LLM parsing and normalization."""

from __future__ import annotations

import json

import pytest
from agate_nodes.person_extract.llm_person_parse import person_from_llm_entry
from agate_nodes.person_extract.person_schemas import ExtractedPerson


def test_person_from_llm_entry_flat_name() -> None:
    person = person_from_llm_entry(
        {
            "name": "Jane Doe",
            "title": "Mayor",
            "affiliation": "City of Chicago",
            "public_figure": True,
            "type": "politician",
            "role_in_story": "Announced policy",
            "nature": "official",
            "nature_secondary_tags": ["source"],
            "mentions": [{"text": "Mayor Jane Doe announced policy.", "quote": False}],
        }
    )
    assert person.name == "Jane Doe"
    assert person.sort_key == "doe"
    assert person.nature == "official"
    assert person.nature_secondary_tags == ["source"]
    assert person.type == "politician"


def test_person_from_llm_entry_accepts_legacy_name_object() -> None:
    person = person_from_llm_entry(
        {
            "name": {"full": "John Smith", "first": "John", "last": "Smith"},
            "role_in_story": "Central figure",
            "nature": "subject",
            "mentions": [{"text": "John Smith spoke at the rally.", "quote": False}],
        }
    )
    assert person.name == "John Smith"
    assert person.sort_key == "smith"


def test_person_from_llm_entry_uses_explicit_sort_key() -> None:
    person = person_from_llm_entry(
        {
            "name": "Jane Doe",
            "sort_key": "custom",
            "role_in_story": "Mentioned",
            "nature": "other",
            "mentions": [{"text": "Jane Doe was there.", "quote": False}],
        }
    )
    assert person.sort_key == "custom"


def test_person_from_llm_entry_invalid_nature_becomes_other() -> None:
    person = person_from_llm_entry(
        {
            "name": "Pat Lee",
            "role_in_story": "Mentioned briefly",
            "nature": "not-a-real-nature",
            "mentions": [{"text": "Pat Lee was there.", "quote": False}],
        }
    )
    assert person.nature == "other"


def test_person_from_llm_entry_requires_mentions() -> None:
    with pytest.raises(ValueError, match="mentions"):
        person_from_llm_entry(
            {
                "name": "No Mentions",
                "role_in_story": "Missing mentions",
                "nature": "other",
                "mentions": [],
            }
        )


def test_extracted_person_serializes_for_worker() -> None:
    person = ExtractedPerson(
        name="Sam Rivera",
        title="Shortstop",
        affiliation="Chicago Cubs",
        public_figure=True,
        type="athlete",
        role_in_story="Guest at ribbon-cutting",
        nature="participant",
        nature_secondary_tags=[],
        mentions=[{"text": "Sam Rivera attended the event.", "quote": False}],
    )
    payload = person.model_dump()
    assert payload["name"] == "Sam Rivera"
    assert payload["type"] == "athlete"
    assert json.dumps(payload)
