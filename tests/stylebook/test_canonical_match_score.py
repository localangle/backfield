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
    policy_match_score,
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


def test_loose_normalization_treats_punctuation_variants_as_exact() -> None:
    sub = SubstrateMatchInput(
        name="West Garfield Park",
        normalized_name="west garfield park chicago il",
    )
    feat = CanonicalMatchFeatures(
        canonical_id=1,
        label="West Garfield Park, Chicago, IL",
        normalized_aliases=(),
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


def test_combined_score_never_below_string_only() -> None:
    chicago = {"type": "Point", "coordinates": [-87.6298, 41.8781]}
    far = {"type": "Point", "coordinates": [-100.0, 35.0]}
    sub = SubstrateMatchInput(
        name="Hello World",
        normalized_name="hello world",
        geometry_json=chicago,
    )
    feat = CanonicalMatchFeatures(
        canonical_id=1,
        label="hello earth",
        normalized_aliases=("hello earth",),
        geometry_json=far,
    )
    s_str = string_score_for_candidate(sub, feat)
    comb = combined_score(sub, feat)
    assert comb >= s_str


def test_state_abbrev_vs_full_name_token_coverage() -> None:
    sub = SubstrateMatchInput(
        name="Chicago, IL",
        normalized_name="chicago, il",
    )
    feat = CanonicalMatchFeatures(
        canonical_id=1,
        label="Chicago, Illinois",
        normalized_aliases=(),
    )
    assert string_score_for_candidate(sub, feat) >= AUTOLINK_MIN_SCORE


def test_formatted_address_extra_tokens_match_canonical_label() -> None:
    """Geocoder formatted lines often extend the display name; label tokens still match."""
    sub = SubstrateMatchInput(
        name="West Garfield Park, Chicago, IL",
        normalized_name="west garfield park west side chicago il usa",
        formatted_address="West Garfield Park, West Side, Chicago, IL, USA",
    )
    feat = CanonicalMatchFeatures(
        canonical_id=1,
        label="West Garfield Park, Chicago, IL",
        normalized_aliases=(),
    )
    assert string_score_for_candidate(sub, feat) >= AUTOLINK_MIN_SCORE


def test_policy_match_non_address_ignores_spatial_penalty() -> None:
    chicago = {"type": "Point", "coordinates": [-87.6298, 41.8781]}
    far = {"type": "Point", "coordinates": [-70.0, 40.0]}
    sub = SubstrateMatchInput(
        name="West Garfield Park",
        normalized_name="west garfield park chicago il",
        geometry_json=chicago,
    )
    feat = CanonicalMatchFeatures(
        canonical_id=1,
        label="West Garfield Park, Chicago, IL",
        normalized_aliases=(),
        geometry_json=far,
    )
    s_str = string_score_for_candidate(sub, feat)
    p_neighborhood = policy_match_score(sub, feat, substrate_location_type="neighborhood")
    p_address = policy_match_score(sub, feat, substrate_location_type="address")
    assert s_str == 1.0
    assert p_neighborhood == 1.0
    assert p_address >= s_str
