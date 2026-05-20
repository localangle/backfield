"""PlaceExtract ``mentions`` normalization."""

from agate_nodes.place_extract.mentions import (
    mention_texts_for_persist,
    normalize_location_mentions,
    parse_mentions_from_location_data,
)


def test_parse_mentions_from_location_data() -> None:
    raw = {
        "mentions": [
            {"text": " First mention. "},
            {"text": "Second mention."},
            "invalid",
        ]
    }
    assert parse_mentions_from_location_data(raw) == [
        {"text": "First mention."},
        {"text": "Second mention."},
    ]


def test_normalize_from_original_text_only() -> None:
    out = normalize_location_mentions({"original_text": "Hello Ohio."})
    assert out["original_text"] == "Hello Ohio."
    assert out["mentions"] == [{"text": "Hello Ohio."}]


def test_normalize_from_mentions_sets_original_text() -> None:
    out = normalize_location_mentions(
        {
            "mentions": [
                {"text": "Ohio in the lede."},
                {"text": "Back in Ohio later."},
            ],
            "original_text": "stale",
        }
    )
    assert out["original_text"] == "Ohio in the lede."
    assert len(out["mentions"]) == 2


def test_mention_texts_for_persist() -> None:
    entry = {
        "mentions": [{"text": "A"}, {"text": "B"}],
        "original_text": "A",
    }
    assert mention_texts_for_persist(entry) == ["A", "B"]


def test_geocode_extra_fields_preserve_mentions() -> None:
    """GeocodeAgent copies keys other than location/original_text (including mentions)."""
    loc = normalize_location_mentions(
        {
            "original_text": "Ohio lawmakers advanced the bill.",
            "mentions": [
                {"text": "Ohio lawmakers advanced the bill."},
                {"text": "Back in Ohio, the governor signed it."},
            ],
            "location": {"full": "Ohio", "type": "state", "components": {}},
            "type": "state",
        }
    )
    extra_fields = {
        key: value
        for key, value in loc.items()
        if key not in ("location", "original_text")
    }
    assert extra_fields["mentions"] == loc["mentions"]
    assert len(extra_fields["mentions"]) == 2
