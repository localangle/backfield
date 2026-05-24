"""Tests for ``processed_item_reviewed_output``."""

from __future__ import annotations

from api.processed_item_reviewed_output import (
    build_reviewed_output,
    overlay_has_review_content,
)


def _place(desc: str, **extra: object) -> dict:
    return {
        "description": desc,
        "original_text": "t",
        "location": {"full": "Minneapolis, MN", "type": "city", "components": {}},
        **extra,
    }


def _empty_areas() -> dict:
    return {
        "states": [],
        "counties": [],
        "cities": [],
        "neighborhoods": [],
        "regions": [],
        "other": [],
    }


def _geocode_output(
    *,
    points: list[dict] | None = None,
    cities: list[dict] | None = None,
    node_id: str = "geocode_agent",
) -> dict:
    areas = _empty_areas()
    if cities:
        areas["cities"] = cities
    return {
        node_id: {
            "places": {
                "areas": areas,
                "points": points or [],
                "needs_review": [],
            },
        },
    }


def test_overlay_has_review_content_false_when_empty() -> None:
    assert overlay_has_review_content(None) is False
    assert overlay_has_review_content({}) is False
    assert overlay_has_review_content({"locations": {"by_anchor": {}, "user_added": []}}) is False


def test_overlay_has_review_content_true_for_patch() -> None:
    assert overlay_has_review_content(
        {"locations": {"by_anchor": {"p1": {"description": "x"}}}}
    )


def test_overlay_has_review_content_true_for_article_key_even_when_empty() -> None:
    assert overlay_has_review_content({"article": {"headline": ""}})


def test_build_reviewed_output_none_without_review() -> None:
    output = _geocode_output(cities=[_place("a", id="p1")])
    assert build_reviewed_output(output, None) is None
    assert build_reviewed_output(output, {}) is None


def test_build_reviewed_output_applies_description_patch() -> None:
    output = _geocode_output(cities=[_place("orig", id="p1")])
    overlay = {"locations": {"by_anchor": {"p1": {"description": "edited"}}}}
    reviewed = build_reviewed_output(output, overlay)
    assert reviewed is not None
    places = reviewed["geocode_agent"]["places"]
    assert places["areas"]["cities"][0]["description"] == "edited"


def test_build_reviewed_output_applies_geometry_patch() -> None:
    geom = {"type": "Point", "coordinates": [-93.27, 44.98]}
    output = _geocode_output(
        points=[_place("pt", id="p1", geocode={"geocode_type": "pelias", "result": {}})],
    )
    overlay = {
        "locations": {
            "by_anchor": {
                "p1": {
                    "geocode": {
                        "geocode_type": "manual",
                        "result": {"geometry": geom},
                    }
                }
            }
        }
    }
    reviewed = build_reviewed_output(output, overlay)
    assert reviewed is not None
    pt = reviewed["geocode_agent"]["places"]["points"][0]
    assert pt["geocode"]["result"]["geometry"] == geom


def test_build_reviewed_output_removes_anchor() -> None:
    output = _geocode_output(
        cities=[_place("keep", id="k1"), _place("gone", id="g1")],
    )
    overlay = {"locations": {"removed_anchors": ["g1"]}}
    reviewed = build_reviewed_output(output, overlay)
    assert reviewed is not None
    cities = reviewed["geocode_agent"]["places"]["areas"]["cities"]
    assert len(cities) == 1
    assert cities[0]["description"] == "keep"


def test_build_reviewed_output_user_added_geometry_json_output_only() -> None:
    geom = {"type": "Point", "coordinates": [-93.27, 44.98]}
    uid = "user_place:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    output = {
        "json_output": {
            "consolidated": {
                "headline": "Story",
                "places": {
                    "areas": _empty_areas(),
                    "points": [],
                    "needs_review": [],
                },
            },
        },
    }
    overlay = {
        "locations": {
            "user_added": [
                {
                    "id": uid,
                    "location": _place(
                        "manual",
                        geocode={"geocode_type": "manual", "result": {"geometry": geom}},
                    ),
                }
            ]
        }
    }
    reviewed = build_reviewed_output(output, overlay)
    assert reviewed is not None
    points = reviewed["json_output"]["consolidated"]["places"]["points"]
    assert len(points) == 1
    assert points[0]["geocode"]["result"]["geometry"] == geom


def test_build_reviewed_output_user_added_in_points() -> None:
    output = _geocode_output(cities=[_place("m", id="mid")])
    uid = "user_place:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    overlay = {
        "locations": {
            "user_added": [
                {
                    "id": uid,
                    "location": _place("manual"),
                }
            ]
        }
    }
    reviewed = build_reviewed_output(output, overlay)
    assert reviewed is not None
    points = reviewed["geocode_agent"]["places"]["points"]
    assert len(points) == 1
    assert points[0]["description"] == "manual"


def test_build_reviewed_output_syncs_json_output_consolidated() -> None:
    places = {
        "areas": _empty_areas(),
        "points": [_place("x", id="p1")],
        "needs_review": [],
    }
    output = {
        "geocode_agent": {"places": places},
        "json_output": {
            "consolidated": {
                "headline": "Old",
                "places": {
                    "areas": _empty_areas(),
                    "points": [_place("x", id="p1")],
                    "needs_review": [],
                },
            },
        },
    }
    overlay = {"locations": {"by_anchor": {"p1": {"description": "reviewed"}}}}
    reviewed = build_reviewed_output(output, overlay)
    assert reviewed is not None
    assert reviewed["geocode_agent"]["places"]["points"][0]["description"] == "reviewed"
    json_places = reviewed["json_output"]["consolidated"]["places"]
    assert json_places["points"][0]["description"] == "reviewed"


def test_build_reviewed_output_article_on_consolidated() -> None:
    output = {
        "geocode_agent": {"places": {"areas": _empty_areas(), "points": [], "needs_review": []}},
        "json_output": {
            "consolidated": {
                "headline": "Model headline",
                "publication": "Model pub",
            },
        },
    }
    overlay = {"article": {"headline": "Review headline", "publication": "Review pub"}}
    reviewed = build_reviewed_output(output, overlay)
    assert reviewed is not None
    consolidated = reviewed["json_output"]["consolidated"]
    assert consolidated["headline"] == "Review headline"
    assert consolidated["publication"] == "Review pub"


def test_build_reviewed_output_article_on_hoisted_stylebook_output() -> None:
    output = {
        "geocode_agent": {"places": {"areas": _empty_areas(), "points": [], "needs_review": []}},
        "stylebook_output": {
            "headline": "Model headline",
            "publication": "Model pub",
            "places": {"areas": _empty_areas(), "points": [], "needs_review": []},
            "success": True,
            "article_id": 42,
        },
    }
    overlay = {"article": {"headline": "Review headline", "author": "Pat"}}
    reviewed = build_reviewed_output(output, overlay)
    assert reviewed is not None
    so = reviewed["stylebook_output"]
    assert so["headline"] == "Review headline"
    assert so["author"] == "Pat"
    assert so["publication"] == "Model pub"
    assert reviewed["geocode_agent"]["places"]["points"] == []
