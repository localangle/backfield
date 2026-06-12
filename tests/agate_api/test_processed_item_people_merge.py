"""Unit tests for ``api.processed_item.entities.person.people_merge``."""

from __future__ import annotations

from api.processed_item.entities.person.people_merge import build_merged_people_lane


def _person(name: str, **extra: object) -> dict:
    return {
        "name": name,
        "title": "",
        "affiliation": "",
        "public_figure": False,
        "type": "",
        "role_in_story": "",
        "nature": "other",
        "nature_secondary_tags": [],
        "mentions": [{"text": f"Mention of {name}.", "quote": False}],
        **extra,
    }


def _people_output(*, people: list[dict], node_id: str = "stylebook_output") -> dict:
    return {node_id: {"people": people, "success": True}}


def test_merge_model_only_empty_overlay() -> None:
    output = _people_output(people=[_person("Jane Doe", id="p1")])
    merged, stale = build_merged_people_lane(output=output, overlay=None)
    assert stale == []
    assert len(merged) == 1
    assert merged[0]["anchor"] == "p1"
    assert merged[0]["person"]["name"] == "Jane Doe"


def test_merge_shallow_patch_by_anchor() -> None:
    output = _people_output(people=[_person("Jane Doe", id="p1")])
    overlay = {"people": {"by_anchor": {"p1": {"title": "Mayor"}}}}
    merged, stale = build_merged_people_lane(output=output, overlay=overlay)
    assert stale == []
    assert merged[0]["person"]["title"] == "Mayor"


def test_merge_removed_anchor() -> None:
    output = _people_output(people=[_person("Jane Doe", id="p1"), _person("John Smith", id="p2")])
    overlay = {"people": {"removed_anchors": ["p1"]}}
    merged, _stale = build_merged_people_lane(output=output, overlay=overlay)
    assert len(merged) == 1
    assert merged[0]["anchor"] == "p2"


def test_merge_json_output_consolidated_baseline() -> None:
    output = {
        "person_extract": {"people": [_person("Extract only", id="x1")], "success": True},
        "json_output": {
            "consolidated": {
                "headline": "Story",
                "people": [_person("Jane Doe", id="p1")],
            },
        },
    }
    merged, stale = build_merged_people_lane(output=output, overlay=None)
    assert stale == []
    assert len(merged) == 1
    assert merged[0]["anchor"] == "p1"
    assert merged[0]["node_id"] == "json_output"
    assert merged[0]["person"]["name"] == "Jane Doe"
