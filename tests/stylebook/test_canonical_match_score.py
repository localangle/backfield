"""Unit tests for pure canonical match scoring (no DB)."""

from __future__ import annotations

import math

from backfield_stylebook.canonical_match_score import (
    AUTOLINK_MIN_SCORE,
    RECALL_MIN_SCORE,
    CanonicalMatchFeatures,
    SubstrateMatchInput,
    classify_recall_score,
    combined_score,
    haversine_m,
    spatial_score_from_distance_m,
    string_score_for_candidate,
)


def test_string_score_exact_normalized_alias() -> None:
    sub = SubstrateMatchInput(
        name="West Garfield Park, Chicago, IL",
        normalized_name="west garfield park, chicago, il",
    )
    feat = CanonicalMatchFeatures(
        canonical_id=1,
        label="Other",
        normalized_aliases=("west garfield park, chicago, il",),
    )
    assert string_score_for_candidate(sub, feat) == 1.0


def test_string_score_fuzzy_close_strings() -> None:
    sub = SubstrateMatchInput(
        name="West Garfield Park, Chicago, IL",
        normalized_name="west garfield park, chicago, il",
    )
    feat = CanonicalMatchFeatures(
        canonical_id=1,
        label="West Garfield Park, Chicago, IL",
        normalized_aliases=("west garfield park chicago il",),
    )
    s = string_score_for_candidate(sub, feat)
    assert s >= AUTOLINK_MIN_SCORE


def test_combined_score_boosts_when_geometry_agrees() -> None:
    pt = {"type": "Point", "coordinates": [-87.73, 41.88]}
    sub = SubstrateMatchInput(
        name="X",
        normalized_name="x",
        geometry_json=pt,
    )
    feat = CanonicalMatchFeatures(
        canonical_id=1,
        label="x",
        normalized_aliases=("x",),
        geometry_json=pt,
    )
    assert combined_score(sub, feat) == 1.0


def test_spatial_score_decays_with_distance() -> None:
    chicago = (41.8781, -87.6298)
    nearby = (41.88, -87.63)
    d = haversine_m(chicago, nearby)
    s = spatial_score_from_distance_m(d)
    assert s is not None
    assert 0.0 < s < 1.0
    assert spatial_score_from_distance_m(0.0) == 1.0


def test_classify_recall_score_bands() -> None:
    assert classify_recall_score(AUTOLINK_MIN_SCORE) == "autolink"
    assert classify_recall_score(RECALL_MIN_SCORE) == "ambiguous"
    assert classify_recall_score(RECALL_MIN_SCORE - 0.01) == "below_recall"


def test_haversine_symmetric() -> None:
    a = (41.0, -87.0)
    b = (42.0, -88.0)
    assert math.isclose(haversine_m(a, b), haversine_m(b, a))
