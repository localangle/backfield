"""Tests for schedule scoreboard school normalization."""

from __future__ import annotations

from agate_nodes.place_extract.mentions_build import build_mentions
from agate_nodes.place_extract.schedule_matchups import (
    extract_schedule_matchups,
    find_schedule_line_for_school,
)
from agate_nodes.place_extract.schedule_school_normalize import (
    normalize_location_entries,
    prepare_location_dict_for_geocode,
)

ARTICLE_SNIPPET = """
Wauconda 85, Woodstock North 49

Beacon at Northtown

Hinsdale Adventist at Calvary Christian

Wolcott at Rochelle Zell

Quarterfinals (at Somonauk)
"""


def test_extract_schedule_matchups_finds_both_sides() -> None:
    pairs = extract_schedule_matchups(ARTICLE_SNIPPET)
    assert ("Hinsdale Adventist", "Calvary Christian") in pairs
    assert ("Wolcott", "Rochelle Zell") in pairs
    assert all("(" not in away and "(" not in home for away, home in pairs)


def test_find_schedule_line_for_school() -> None:
    assert (
        find_schedule_line_for_school(ARTICLE_SNIPPET, "Rochelle Zell")
        == "Wolcott at Rochelle Zell"
    )
    assert (
        find_schedule_line_for_school(ARTICLE_SNIPPET, "Hinsdale Adventist")
        == "Hinsdale Adventist at Calvary Christian"
    )


def test_normalize_adds_missing_away_team_and_coerces_other() -> None:
    entries = [
        {
            "location": "Calvary Christian",
            "type": "other",
            "description": "Schedule matchup school (home).",
            "geocode_hints": "",
            "nature": "unknown",
            "components": {"city": "Calvary Christian"},
        },
        {
            "location": "Rochelle Zell",
            "type": "other",
            "description": "School listed in the schedule for a matchup against Wolcott.",
            "geocode_hints": "",
            "nature": "unknown",
            "components": {"city": "Rochelle Zell"},
        },
    ]
    normalized = normalize_location_entries(ARTICLE_SNIPPET, entries)
    names = set()
    for item in normalized:
        if item.get("type") != "place":
            continue
        place_name = item.get("components", {}).get("place", {}).get("name")
        label = str(place_name or item["location"]).split(",")[0]
        names.add(label)
    assert "Hinsdale Adventist" in names
    assert "Calvary Christian" in names
    assert "Wolcott" in names
    assert "Rochelle Zell" in names
    for item in normalized:
        if item.get("type") == "place" and item.get("components", {}).get("place"):
            assert item["components"]["city"] == ""


def test_build_mentions_uses_single_schedule_line_for_place() -> None:
    mentions = build_mentions(ARTICLE_SNIPPET, "Rochelle Zell, IL", "place")
    assert mentions == [{"text": "Wolcott at Rochelle Zell"}]


def test_prepare_location_dict_for_geocode_upgrades_other_to_place() -> None:
    loc = {
        "original_text": "Hinsdale Adventist at Calvary Christian",
        "description": "School listed in the schedule.",
        "location": {
            "full": "Hinsdale Adventist",
            "type": "other",
            "components": {"city": "Hinsdale Adventist"},
        },
    }
    prepared = prepare_location_dict_for_geocode(loc, ARTICLE_SNIPPET)
    assert prepared["location"]["type"] == "place"
    assert prepared["location"]["components"]["place"]["name"] == "Hinsdale Adventist"
    assert prepared["mentions"] == [{"text": "Hinsdale Adventist at Calvary Christian"}]
