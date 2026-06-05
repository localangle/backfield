"""Unit tests for pure canonical match scoring (no DB)."""

from __future__ import annotations

import math

from backfield_stylebook.canonical_match_score import (
    AUTOLINK_MIN_SCORE,
    RECALL_MIN_SCORE,
    CanonicalMatchFeatures,
    SubstrateMatchInput,
    _loose_key,
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
        canonical_id="1",
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
        canonical_id="1",
        label="West Garfield Park, Chicago, IL",
        normalized_aliases=(),
    )
    assert string_score_for_candidate(sub, feat) == 1.0


def test_ordinal_suffix_normalization_makes_ward_variants_match() -> None:
    sub = SubstrateMatchInput(
        name="15th Ward, Chicago, IL",
        normalized_name="15th ward, chicago, il",
    )
    feat = CanonicalMatchFeatures(
        canonical_id="1",
        label="Ward 15, Chicago, IL",
        normalized_aliases=("ward 15, chicago, il",),
    )
    assert string_score_for_candidate(sub, feat) >= AUTOLINK_MIN_SCORE


def test_word_ordinal_normalization_matches_digit_congressional_district() -> None:
    sub = SubstrateMatchInput(
        name="Fifth Congressional District, Illinois",
        normalized_name="fifth congressional district, illinois",
    )
    feat = CanonicalMatchFeatures(
        canonical_id="1",
        label="Congressional District 5, Illinois",
        normalized_aliases=("congressional district 5, illinois",),
    )
    assert string_score_for_candidate(sub, feat) >= AUTOLINK_MIN_SCORE


def test_compound_word_ordinal_twenty_first_normalizes() -> None:
    sub = SubstrateMatchInput(
        name="Illinois Congressional District Twenty-First",
        normalized_name="illinois congressional district twenty-first",
    )
    feat = CanonicalMatchFeatures(
        canonical_id="1",
        label="Congressional District 21, Illinois",
        normalized_aliases=("congressional district 21, illinois",),
    )
    assert string_score_for_candidate(sub, feat) >= AUTOLINK_MIN_SCORE


def test_fifty_third_spelled_ordinal_matches_digit_district() -> None:
    sub = SubstrateMatchInput(
        name="Fifty-Third Congressional District, Illinois",
        normalized_name="fifty-third congressional district, illinois",
    )
    feat = CanonicalMatchFeatures(
        canonical_id="1",
        label="Congressional District 53, Illinois",
        normalized_aliases=("congressional district 53, illinois",),
    )
    assert string_score_for_candidate(sub, feat) >= AUTOLINK_MIN_SCORE


def test_loose_key_does_not_apply_full_sentence_number_parsing() -> None:
    """Guardrail: do not use ``number_parser.parse`` semantics on whole strings."""
    assert _loose_key("Six Flags, Gurnee, IL") == "six flags gurnee il"
    assert _loose_key("twentyfirst ward") == "21 ward"


def test_string_score_fuzzy_close_strings() -> None:
    sub = SubstrateMatchInput(
        name="West Garfield Park, Chicago, IL",
        normalized_name="west garfield park, chicago, il",
    )
    feat = CanonicalMatchFeatures(
        canonical_id="1",
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
        canonical_id="1",
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
        canonical_id="1",
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
        canonical_id="1",
        label="Chicago, Illinois",
        normalized_aliases=(),
    )
    assert string_score_for_candidate(sub, feat) >= AUTOLINK_MIN_SCORE


def test_formatted_address_extra_tokens_match_canonical_label() -> None:
    """Geocoder formatted lines often extend the display name; label tokens still match.

    The name itself contains all canonical tokens (same place), so identity heuristics
    fire via name surfaces even after formatted_address is excluded from them.
    """
    sub = SubstrateMatchInput(
        name="West Garfield Park, Chicago, IL",
        normalized_name="west garfield park west side chicago il usa",
        formatted_address="West Garfield Park, West Side, Chicago, IL, USA",
    )
    feat = CanonicalMatchFeatures(
        canonical_id="1",
        label="West Garfield Park, Chicago, IL",
        normalized_aliases=(),
    )
    assert string_score_for_candidate(sub, feat) >= AUTOLINK_MIN_SCORE


def test_formatted_address_city_tail_does_not_inflate_score_for_unrelated_place() -> None:
    """formatted_address trailing ', Chicago, IL' must not produce 1.0 via identity heuristics.

    An address or place whose *name* is unrelated to 'Chicago, IL' but whose
    formatted_address contains the city/state tail should score well below the
    autolink threshold against the Chicago, IL canonical.
    """
    sub = SubstrateMatchInput(
        name="1020 W. Sheridan Road, Chicago, IL",
        normalized_name="1020 w. sheridan road, chicago, il",
        formatted_address="1020 West Sheridan Road, North Side, Chicago, IL, USA",
    )
    chicago_feat = CanonicalMatchFeatures(
        canonical_id="1",
        label="Chicago, IL",
        normalized_aliases=("chicago, il",),
    )
    score = string_score_for_candidate(sub, chicago_feat)
    # The score may still be nonzero (ratio on shared tokens), but must not hit 1.0
    # from identity shortcuts triggered only by formatted_address.
    assert score < 1.0, f"Expected score < 1.0 for address vs city canonical, got {score}"


def test_alias_token_coverage_does_not_fire_via_formatted_address() -> None:
    """Alias token coverage must use name-only surfaces, not formatted_address.

    If canonical 'Chicago, IL' accumulated an alias like
    'illinois st. and clark st., chicago, il' (from a prior wrong link), a new
    substrate whose *name* does not contain all alias tokens must not score 1.0.
    """
    sub = SubstrateMatchInput(
        name="39th Street and Kedzie Avenue, Chicago, IL",
        normalized_name="39th street and kedzie avenue, chicago, il",
        formatted_address="S Kedzie Ave and W 39th Pl, Chicago, IL 60632",
    )
    feat = CanonicalMatchFeatures(
        canonical_id="1",
        label="Chicago, IL",
        # Alias that crept in from a prior wrong link (intersection name)
        normalized_aliases=(
            "chicago, il",
            "illinois st. and clark st., chicago, il",
        ),
    )
    score = string_score_for_candidate(sub, feat)
    # "illinois st. and clark st." tokens ("illinois", "clark") are NOT in the
    # substrate *name*, only in formatted_address — so alias coverage must not return 1.0.
    assert score < 1.0, (
        f"Alias token coverage should not fire via formatted_address, got score {score}"
    )


def test_policy_match_non_address_ignores_spatial_penalty() -> None:
    chicago = {"type": "Point", "coordinates": [-87.6298, 41.8781]}
    far = {"type": "Point", "coordinates": [-70.0, 40.0]}
    sub = SubstrateMatchInput(
        name="West Garfield Park",
        normalized_name="west garfield park chicago il",
        geometry_json=chicago,
    )
    feat = CanonicalMatchFeatures(
        canonical_id="1",
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
