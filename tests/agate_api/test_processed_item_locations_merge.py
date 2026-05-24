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
    needs_review: list[dict] | None = None,
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
                "needs_review": needs_review or [],
            },
        },
    }


def test_merge_model_only_empty_overlay() -> None:
    output = _geocode_output(cities=[_place("a", id="m1")])
    merged, stale = build_merged_locations_lane(output=output, overlay=None)
    assert stale == []
    assert len(merged) == 1
    assert merged[0]["anchor"] == "m1"
    assert merged[0]["source"] == "model"
    assert merged[0]["node_id"] == "geocode_agent"
    assert merged[0]["location"]["description"] == "a"


def test_merge_anchor_fallback_uses_node_index() -> None:
    output = _geocode_output(points=[_place("no id")])
    merged, _stale = build_merged_locations_lane(output=output, overlay=None)
    assert merged[0]["anchor"] == "geocode_agent:0"


def test_merge_shallow_patch_by_anchor() -> None:
    output = _geocode_output(cities=[_place("orig", id="p1")])
    overlay = {"locations": {"by_anchor": {"p1": {"description": "edited"}}}}
    merged, stale = build_merged_locations_lane(output=output, overlay=overlay)
    assert stale == []
    assert merged[0]["location"]["description"] == "edited"
    assert merged[0]["location"]["original_text"] == "t"


def test_stale_patch_when_anchor_missing() -> None:
    output = _geocode_output(cities=[_place("only", id="alive")])
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
    output = _geocode_output(cities=[_place("m", id="mid")])
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


def test_user_added_merges_by_anchor_geometry_patch() -> None:
    geom = {"type": "Point", "coordinates": [-93.27, 44.98]}
    uid = "user_place:aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    overlay = {
        "locations": {
            "user_added": [
                {
                    "id": uid,
                    "location": _place("manual"),
                }
            ],
            "by_anchor": {
                uid: {
                    "geocode": {
                        "geocode_type": "manual",
                        "result": {"geometry": geom},
                    }
                }
            },
        }
    }
    merged, _stale = build_merged_locations_lane(output={}, overlay=overlay)
    assert len(merged) == 1
    assert merged[0]["location"]["geocode"]["result"]["geometry"] == geom


def test_user_added_skips_invalid_id() -> None:
    merged, _ = build_merged_locations_lane(
        output={},
        overlay={"locations": {"user_added": [{"id": "bad", "location": _place("x")}]}},
    )
    assert merged == []


def test_mention_id_anchor() -> None:
    output = _geocode_output(cities=[_place("m", mention_id="mention-1")])
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


def test_removed_anchors_hides_model_row() -> None:
    output = _geocode_output(
        cities=[_place("gone", id="rm1"), _place("stay", id="keep")],
    )
    overlay = {"locations": {"removed_anchors": ["rm1"]}}
    merged, stale = build_merged_locations_lane(output=output, overlay=overlay)
    assert stale == []
    anchors = {r["anchor"] for r in merged}
    assert anchors == {"keep"}


def test_merge_distinct_rows_when_point_ids_share_h3_cell() -> None:
    """Colocated POIs must not collapse when GeocodeAgent reuses the same ``h3:`` id."""
    shared_h3 = "h3:8c2664cacb6ddff"
    output = {
        "geo": {
            "places": {
                "points": [
                    {
                        "id": shared_h3,
                        "description": "Salt Shed",
                        "original_text": "perform at Salt Shed",
                        "geocode": {
                            "result": {
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [-87.659194, 41.906741],
                                },
                            },
                        },
                    },
                    {
                        "id": shared_h3,
                        "description": "Oddball Market",
                        "original_text": "Oddball Market attractions",
                        "geocode": {
                            "result": {
                                "geometry": {
                                    "type": "Point",
                                    "coordinates": [-87.659194, 41.906741],
                                },
                            },
                        },
                    },
                ],
            },
        },
    }
    merged, stale = build_merged_locations_lane(output=output, overlay=None)
    assert stale == []
    assert len(merged) == 2
    anchors = {r["anchor"] for r in merged}
    assert anchors == {"geo:0", "geo:1"}
    by_anchor = {r["anchor"]: r for r in merged}
    assert by_anchor["geo:0"]["location"]["description"] == "Salt Shed"
    assert by_anchor["geo:1"]["location"]["description"] == "Oddball Market"


def test_geocode_node_skips_locations_when_places_present() -> None:
    """DBOutput-style payload: one row per site, not PlaceExtract + Geocode duplicates."""
    shared_body = {
        "description": "Gene & Georgetti",
        "original_text": "founded Gene & Georgetti Restaurant at 500 N. Franklin",
        "location": {
            "full": "500 N. Franklin St., Chicago, IL",
            "type": "address",
            "components": {},
        },
    }
    output = {
        "geocode_agent": {
            "locations": [
                {**shared_body, "id": "extract:0"},
                {**shared_body, "description": "Gene's Bistro", "id": "extract:1"},
            ],
            "places": {
                "areas": {
                    "cities": [
                        {
                            "id": "stylebook:chicago",
                            "description": "Chicago context",
                            "original_text": "Chicago institution",
                            "location": "Chicago, IL",
                            "type": "city",
                        }
                    ],
                    "counties": [],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                    "states": [],
                },
                "points": [
                    {
                        "id": "h3:abc",
                        "description": "Gene & Georgetti",
                        "original_text": "500 N. Franklin",
                        "geocode": {
                            "result": {
                                "geometry": {"type": "Point", "coordinates": [-87.63, 41.89]},
                            },
                        },
                    },
                    {
                        "id": "h3:midway",
                        "description": "Gene's Bistro",
                        "original_text": "Gene's Bistro",
                        "geocode": {
                            "result": {
                                "geometry": {"type": "Point", "coordinates": [-87.74, 41.78]},
                            },
                        },
                    },
                ],
            },
        },
    }
    merged, stale = build_merged_locations_lane(output=output, overlay=None)
    assert stale == []
    assert len(merged) == 3
    anchors = {r["anchor"] for r in merged}
    assert "extract:0" not in anchors
    assert "extract:1" not in anchors
    assert "stylebook:chicago" in anchors
    assert "geocode_agent:1" in anchors
    assert "geocode_agent:2" in anchors


def test_place_extract_only_output_yields_no_model_rows() -> None:
    output = {
        "place_extract": {
            "locations": [
                _place("extract only", id="extract:0"),
            ],
        },
    }
    merged, stale = build_merged_locations_lane(output=output, overlay=None)
    assert stale == []
    assert merged == []


def test_place_extract_ignored_when_geocode_places_present() -> None:
    """Cross-node: PlaceExtract ``locations`` must not duplicate Geocode ``places`` rows."""
    hospital = {
        "description": "Presence St. Francis Hospital",
        "original_text": "pronounced dead at Presence St. Francis Hospital in Evanston",
        "location": {
            "full": "Presence St. Francis Hospital, Evanston, IL",
            "type": "place",
            "components": {"place": {"name": "Presence St. Francis Hospital"}},
        },
    }
    evanston = {
        **hospital,
        "description": "Evanston city",
        "location": {"full": "Evanston, IL", "type": "city", "components": {}},
    }
    geocoded = _geocode_output(
        points=[
            {
                "id": "h3:hospital",
                "description": "Presence St. Francis Hospital",
                "original_text": hospital["original_text"],
                "geocode": {
                    "result": {
                        "geometry": {"type": "Point", "coordinates": [-87.68, 42.02]},
                    },
                },
            },
        ],
    )
    output = {"place_extract": {"locations": [hospital, evanston]}, **geocoded}
    merged, stale = build_merged_locations_lane(output=output, overlay=None)
    assert stale == []
    assert len(merged) == 1
    assert merged[0]["node_id"] == "geocode_agent"
    assert merged[0]["anchor"] == "geocode_agent:0"
    assert "place_extract" not in {r["node_id"] for r in merged}


def test_stylebook_output_preferred_over_geocode_agent() -> None:
    """When both nodes carry ``places``, review uses stylebook_output only."""
    point_geom = {"type": "Point", "coordinates": [1.0, 2.0]}
    output = {
        **_geocode_output(
            points=[
                {
                    "id": "geo-only",
                    "description": "from geocode",
                    "geocode": {"result": {"geometry": point_geom}},
                },
            ],
        ),
        "stylebook_output": {
            "places": {
                "areas": _empty_areas(),
                "points": [
                    {
                        "id": "sb-only",
                        "description": "from stylebook",
                        "geocode": {
                            "result": {
                                "geometry": {"type": "Point", "coordinates": [3.0, 4.0]},
                            },
                        },
                    },
                ],
                "needs_review": [],
            },
        },
    }
    merged, stale = build_merged_locations_lane(output=output, overlay=None)
    assert stale == []
    assert len(merged) == 1
    assert merged[0]["node_id"] == "stylebook_output"
    assert merged[0]["anchor"] == "sb-only"
    assert merged[0]["location"]["description"] == "from stylebook"


def test_needs_review_bucket_included_in_review() -> None:
    output = _geocode_output(
        needs_review=[
            {
                "id": "nr:1",
                "description": "failed geocode",
                "original_text": "somewhere vague",
                "geocoded": False,
            },
        ],
    )
    merged, stale = build_merged_locations_lane(output=output, overlay=None)
    assert stale == []
    assert len(merged) == 1
    assert merged[0]["anchor"] == "nr:1"
    assert merged[0]["location"]["description"] == "failed geocode"


def test_places_only_geocode_output() -> None:
    output = _geocode_output(
        points=[
            {
                "id": "p1",
                "geocode": {
                    "result": {"geometry": {"type": "Point", "coordinates": [1.0, 2.0]}},
                },
            },
        ],
        node_id="geo",
    )
    merged, stale = build_merged_locations_lane(output=output, overlay=None)
    assert stale == []
    assert len(merged) == 1
    assert merged[0]["anchor"] == "p1"
