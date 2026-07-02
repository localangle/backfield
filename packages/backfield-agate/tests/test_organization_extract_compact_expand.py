"""Tests for compact OrganizationExtract enum code maps and row expansion."""

from __future__ import annotations

import pytest
from agate_nodes.organization_extract.compact_expand import (
    ORG_NATURE_CODES,
    ORG_NATURE_FROM_CODE,
    ORG_TYPE_CODES,
    ORG_TYPE_FROM_CODE,
    expand_compact_organization_row,
    expand_organization_boundary,
    expand_organization_nature,
    expand_organization_type,
)
from agate_nodes.organization_extract.llm_organization_parse import organization_from_llm_entry
from backfield_entities.entities.organization.review import (
    _BOUNDARY_SHORT_BY_VALUE,
    ORGANIZATION_BOUNDARY_VALUES,
)
from backfield_entities.entities.organization.types import (
    ORGANIZATION_NATURE_VALUES,
    ORGANIZATION_TYPE_VALUES,
)


def test_org_type_codes_cover_all_values() -> None:
    assert set(ORG_TYPE_CODES.keys()) == set(ORGANIZATION_TYPE_VALUES)
    assert len(ORG_TYPE_FROM_CODE) == len(ORG_TYPE_CODES)
    assert set(ORG_TYPE_FROM_CODE.values()) == set(ORG_TYPE_CODES.keys())


def test_org_nature_codes_cover_all_values() -> None:
    assert set(ORG_NATURE_CODES.keys()) == set(ORGANIZATION_NATURE_VALUES)
    assert len(ORG_NATURE_FROM_CODE) == len(ORG_NATURE_CODES)
    assert set(ORG_NATURE_FROM_CODE.values()) == set(ORG_NATURE_CODES.keys())


def test_org_boundary_short_names_resolve() -> None:
    for full, short in _BOUNDARY_SHORT_BY_VALUE.items():
        assert full in ORGANIZATION_BOUNDARY_VALUES
        assert expand_organization_boundary(short) == full


def test_expand_organization_type_round_trips_codes() -> None:
    assert expand_organization_type("gov") == "government"
    assert expand_organization_type("st") == "sports_team"


def test_expand_organization_nature_round_trips_codes() -> None:
    assert expand_organization_nature("ac") == "actor"
    assert expand_organization_nature("rg") == "regulator"


def test_expand_compact_organization_row_builds_full_dict() -> None:
    entry = expand_compact_organization_row(
        [
            "Chicago City Hall",
            "gov",
            "Announced a new park initiative",
            "ac",
            [["Chicago City Hall announced a new park initiative Monday.", 0]],
        ]
    )
    assert entry["name"] == "Chicago City Hall"
    assert entry["type"] == "government"
    assert entry["nature"] == "actor"


def test_expand_compact_organization_row_boundary_extras() -> None:
    entry = expand_compact_organization_row(
        [
            "Dear Abby",
            "med",
            "Advice column central to the story",
            "so",
            [["Dear Abby advised the reader to seek counseling.", 0]],
            {"b": "work_title"},
        ]
    )
    assert entry["organization_boundary"] == "borderline_work_title"


def test_expand_compact_organization_row_boundary_accepts_full_slug() -> None:
    entry = expand_compact_organization_row(
        [
            "Dear Abby",
            "med",
            "Advice column",
            "so",
            [["Dear Abby advised the reader.", 0]],
            {"b": "borderline_work_title"},
        ]
    )
    assert entry["organization_boundary"] == "borderline_work_title"


def test_expand_compact_organization_row_raises_on_non_list() -> None:
    with pytest.raises(ValueError, match="array"):
        expand_compact_organization_row({"name": "Chicago City Hall"})


def test_compact_organization_parity_matches_full_dict() -> None:
    full_entry = {
        "name": "Chicago City Hall",
        "type": "government",
        "role_in_story": "Announced a new park initiative",
        "nature": "actor",
        "nature_secondary_tags": [],
        "mentions": [
            {
                "text": "Chicago City Hall announced a new park initiative Monday.",
                "quote": False,
            }
        ],
    }
    compact_row = [
        "Chicago City Hall",
        "gov",
        "Announced a new park initiative",
        "ac",
        [["Chicago City Hall announced a new park initiative Monday.", 0]],
    ]
    full_org = organization_from_llm_entry(full_entry)
    compact_org = organization_from_llm_entry(expand_compact_organization_row(compact_row))
    assert full_org.model_dump() == compact_org.model_dump()


def test_compact_organization_boundary_parity() -> None:
    full_entry = {
        "name": "Dear Abby",
        "type": "media",
        "organization_boundary": "borderline_work_title",
        "role_in_story": "Advice column central to the story",
        "nature": "source",
        "mentions": [{"text": "Dear Abby advised the reader to seek counseling.", "quote": False}],
    }
    compact_row = [
        "Dear Abby",
        "med",
        "Advice column central to the story",
        "so",
        [["Dear Abby advised the reader to seek counseling.", 0]],
        {"b": "work_title"},
    ]
    full_org = organization_from_llm_entry(full_entry)
    compact_org = organization_from_llm_entry(expand_compact_organization_row(compact_row))
    assert full_org.model_dump() == compact_org.model_dump()
