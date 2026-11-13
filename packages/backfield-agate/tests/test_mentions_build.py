"""Tests for deterministic PlaceExtract mention reconstruction."""

from agate_nodes.place_extract.mentions_build import (
    MAX_MENTIONS_PER_LOCATION,
    build_mentions,
    build_mentions_for_evidence_anchor,
)


def test_dateline_all_caps_match() -> None:
    article = (
        "PITTSBURGH — En marcha, Daniel Palencia de los Cubs presentó un caso convincente.\n\n"
        "Pero con el nativo de Pittsburgh, Ian Happ, conectando su segundo jonrón."
    )
    mentions = build_mentions(article, "Pittsburgh, PA", "city")
    assert mentions
    assert all(set(m.keys()) == {"text"} for m in mentions)
    assert "PITTSBURGH" in mentions[0]["text"] or "Pittsburgh" in mentions[0]["text"]


def test_dedupes_identical_sentences() -> None:
    sentence = "Officers responded to River North, Chicago, IL overnight."
    article = f"{sentence} {sentence}"
    mentions = build_mentions(article, "River North, Chicago, IL", "neighborhood")
    assert len(mentions) == 1


def test_no_match_does_not_synthesize_location_string() -> None:
    mentions = build_mentions("No places here.", "Chicago, IL", "city")
    assert mentions == []


def test_synthetic_location_fallback_is_opt_in() -> None:
    mentions = build_mentions(
        "No places here.",
        "Chicago, IL",
        "city",
        allow_synthetic_fallback=True,
    )
    assert mentions == [{"text": "Chicago, IL"}]


def test_evidence_anchor_builds_article_context_for_normalized_location() -> None:
    article = (
        "Organizers honored LGBTQ+ leaders, including Ald. Jessie Fuentes (26th), "
        "who walked in the parade."
    )
    mentions = build_mentions_for_evidence_anchor(article, "Ald. Jessie Fuentes (26th)")
    assert mentions == [{"text": article}]


def test_mention_output_is_text_only() -> None:
    article = "Crash on I-290 and Pulaski Road, Chicago, IL closed lanes."
    mentions = build_mentions(
        article,
        "I-290 and Pulaski Road, Chicago, IL",
        "intersection_highway",
    )
    assert mentions
    assert all(set(item.keys()) == {"text"} for item in mentions)


def test_mention_cap() -> None:
    sentence = "Events unfolded in Chicago, IL again."
    article = " ".join(sentence for _ in range(MAX_MENTIONS_PER_LOCATION + 3))
    mentions = build_mentions(article, "Chicago, IL", "city")
    assert len(mentions) <= MAX_MENTIONS_PER_LOCATION


def test_place_mention_finds_name_in_schedule_style_line() -> None:
    article = "Beacon at Northtown\n\nHinsdale Adventist at Calvary Christian\n"
    mentions = build_mentions(article, "Hinsdale Adventist, IL", "place")
    assert mentions == [{"text": "Hinsdale Adventist at Calvary Christian"}]


def test_mention_context_prefers_sentence_within_paragraph() -> None:
    article = (
        "MINNEAPOLIS — City leaders announced a pilot.\n\n"
        "Standing near the Midtown Greenway, Mayor Frey said the program would begin in Powderhorn."
    )
    mentions = build_mentions(article, "Powderhorn, Minneapolis, MN", "neighborhood")
    assert len(mentions) == 1
    assert "Powderhorn" in mentions[0]["text"]
    assert "Midtown Greenway" in mentions[0]["text"]
    assert "MINNEAPOLIS" not in mentions[0]["text"]


def test_mention_context_preserves_abbreviation_periods() -> None:
    article = (
        "Dr. Smith spoke in St. Paul yesterday evening. "
        "U.S. officials left Monday."
    )
    mentions = build_mentions(article, "St. Paul, MN", "city")
    assert mentions == [
        {"text": "Dr. Smith spoke in St. Paul yesterday evening."},
    ]


def test_mention_context_does_not_reuse_st_from_street_suffix() -> None:
    article = (
        "Dr. Smith spoke in St. Paul yesterday. "
        "Ald. Jessie Fuentes joined later near 10 Downing St. Neighbors watched."
    )
    mentions = build_mentions(article, "St. Paul, MN", "city")
    assert mentions == [
        {"text": "Dr. Smith spoke in St. Paul yesterday."},
    ]


def test_evidence_anchor_preserves_abbreviation_sentence() -> None:
    article = (
        "Organizers honored leaders, including Ald. Jessie Fuentes (26th), "
        "who walked near St. Paul Avenue after the parade."
    )
    mentions = build_mentions_for_evidence_anchor(article, "Ald. Jessie Fuentes (26th)")
    assert mentions == [{"text": article}]
