"""Unit tests for ``processed_item_locations_merge``."""

from __future__ import annotations

from api.processed_item_locations_merge import build_merged_locations_lane


def _place(desc: str, **extra: object) -> dict:
    return {
        "description": desc,
        "original_text": "t",
        "location": {"full": "Minneapolis, MN", "type": "city", "components": {}},
        **extra,
    }


def test_merge_model_only_empty_overlay() -> None:
    output = {
        "n1": {
            "text": "x",
            "locations": [
                _place("a", id="m1"),
            ],
        }
    }
    merged, stale = build_merged_locations_lane(output=output, overlay=None)
    assert stale == []
    assert len(merged) == 1
    assert merged[0]["anchor"] == "m1"
    assert merged[0]["source"] == "model"
    assert merged[0]["node_id"] == "n1"
    assert merged[0]["location"]["description"] == "a"


def test_merge_anchor_fallback_uses_node_index() -> None:
    output = {"nx": {"locations": [_place("no id")]}}
    merged, _stale = build_merged_locations_lane(output=output, overlay=None)
    assert merged[0]["anchor"] == "nx:0"


def test_merge_shallow_patch_by_anchor() -> None:
    output = {"n1": {"locations": [_place("orig", id="p1")]}}
    overlay = {"locations": {"by_anchor": {"p1": {"description": "edited"}}}}
    merged, stale = build_merged_locations_lane(output=output, overlay=overlay)
    assert stale == []
    assert merged[0]["location"]["description"] == "edited"
    assert merged[0]["location"]["original_text"] == "t"


def test_stale_patch_when_anchor_missing() -> None:
    output = {"n1": {"locations": [_place("only", id="alive")]}}
    overlay = {
        "locations": {
            "by_anchor": {
                "gone": {"description": "orphan"},
            }
        }
    }
    merged, stale = build_merged_locations_lane(output=output, overlay=overlay)
    assert len(merged) == 1
    assert merged[0]["anchor"] == "alive"
    assert len(stale) == 1
    assert stale[0]["anchor"] == "gone"
    assert stale[0]["reason"] == "anchor_missing_from_model_output"


def test_user_added_locations() -> None:
    output = {"n1": {"locations": [_place("m", id="mid")]}}
    overlay = {
        "locations": {
            "user_added": [
                {
                    "id": "user_place:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                    "location": _place("manual"),
                }
            ]
        }
    }
    merged, stale = build_merged_locations_lane(output=output, overlay=overlay)
    assert stale == []
    anchors = {r["anchor"]: r for r in merged}
    assert "mid" in anchors and anchors["mid"]["source"] == "model"
    uid = "user_place:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert uid in anchors
    assert anchors[uid]["source"] == "user"
    assert anchors[uid]["location"]["description"] == "manual"


def test_user_added_skips_invalid_id() -> None:
    merged, _ = build_merged_locations_lane(
        output={},
        overlay={"locations": {"user_added": [{"id": "bad", "location": _place("x")}]}},
    )
    assert merged == []


def test_mention_id_anchor() -> None:
    output = {"n1": {"locations": [_place("m", mention_id="mention-1")]}}
    merged, _ = build_merged_locations_lane(
        output=output,
        overlay={"locations": {"by_anchor": {"mention-1": {"description": "z"}}}},
    )
    assert merged[0]["location"]["description"] == "z"


def test_places_bucket_supersedes_locations_same_anchor() -> None:
    """Geocode ``places`` rows share anchors with PlaceExtract and carry geometry for review."""
    output = {
        "extract": {
            "locations": [
                _place(
                    "pre-geocode",
                    id="L1",
                    geocode=None,
                ),
            ],
        },
        "geo": {
            "places": {
                "points": [
                    {
                        "id": "L1",
                        "description": "geocoded",
                        "original_text": "t",
                        "geocode": {
                            "geocode_type": "pelias",
                            "result": {
                                "geometry": {"type": "Point", "coordinates": [-93.0, 45.0]},
                            },
                        },
                    },
                ],
            },
        },
    }
    merged, stale = build_merged_locations_lane(output=output, overlay=None)
    assert stale == []
    assert len(merged) == 1
    assert merged[0]["anchor"] == "L1"
    assert merged[0]["node_id"] == "geo"
    geom = merged[0]["location"]["geocode"]["result"]["geometry"]
    assert geom["type"] == "Point"
    assert geom["coordinates"] == [-93.0, 45.0]


def test_places_only_geocode_output() -> None:
    output = {
        "geo": {
            "places": {
                "points": [
                    {
                        "id": "p1",
                        "geocode": {
                            "result": {"geometry": {"type": "Point", "coordinates": [1.0, 2.0]}},
                        },
                    },
                ],
            },
        },
    }
    merged, stale = build_merged_locations_lane(output=output, overlay=None)
    assert stale == []
    assert len(merged) == 1
    assert merged[0]["anchor"] == "p1"
