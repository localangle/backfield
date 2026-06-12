"""Unit tests for ``api.processed_item.entities.organization.organizations_merge``."""

from __future__ import annotations

from api.processed_item.entities.organization.organizations_merge import (
    build_merged_organizations_lane,
)


def _organization(name: str, **extra: object) -> dict:
    return {
        "name": name,
        "type": "",
        "role_in_story": "",
        "nature": "other",
        "nature_secondary_tags": [],
        "mentions": [{"text": f"Mention of {name}.", "quote": False}],
        **extra,
    }


def _organizations_output(*, organizations: list[dict], node_id: str = "stylebook_output") -> dict:
    return {node_id: {"organizations": organizations, "success": True}}


def test_merge_model_only_empty_overlay() -> None:
    output = _organizations_output(organizations=[_organization("City Hall", id="o1")])
    merged, stale = build_merged_organizations_lane(output=output, overlay=None)
    assert stale == []
    assert len(merged) == 1
    assert merged[0]["anchor"] == "o1"
    assert merged[0]["organization"]["name"] == "City Hall"


def test_merge_shallow_patch_by_anchor() -> None:
    output = _organizations_output(organizations=[_organization("City Hall", id="o1")])
    overlay = {"organizations": {"by_anchor": {"o1": {"type": "government"}}}}
    merged, stale = build_merged_organizations_lane(output=output, overlay=overlay)
    assert stale == []
    assert merged[0]["organization"]["type"] == "government"


def test_merge_removed_anchor() -> None:
    output = _organizations_output(
        organizations=[
            _organization("City Hall", id="o1"),
            _organization("Police Dept", id="o2"),
        ]
    )
    overlay = {"organizations": {"removed_anchors": ["o1"]}}
    merged, _stale = build_merged_organizations_lane(output=output, overlay=overlay)
    assert len(merged) == 1
    assert merged[0]["anchor"] == "o2"


def test_merge_json_output_consolidated_baseline() -> None:
    output = {
        "organization_extract": {
            "organizations": [_organization("Extract only", id="x1")],
            "success": True,
        },
        "json_output": {
            "consolidated": {
                "headline": "Story",
                "organizations": [_organization("City Hall", id="o1")],
            },
        },
    }
    merged, stale = build_merged_organizations_lane(output=output, overlay=None)
    assert stale == []
    assert len(merged) == 1
    assert merged[0]["anchor"] == "o1"
    assert merged[0]["node_id"] == "json_output"
    assert merged[0]["organization"]["name"] == "City Hall"
