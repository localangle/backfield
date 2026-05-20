"""Processed-item mention occurrence merge helpers."""

from __future__ import annotations

from api.processed_item_mention_occurrences import (
    build_mention_occurrences_for_row,
    merge_occurrence_lists,
    occurrences_from_place_dict,
)


def test_occurrences_from_place_dict_mentions() -> None:
    place = {
        "original_text": "first",
        "mentions": [{"text": "first"}, {"text": "second"}],
    }
    occ = occurrences_from_place_dict(place)
    assert len(occ) == 2
    assert occ[0]["mention_text"] == "first"
    assert occ[1]["mention_text"] == "second"


def test_merge_occurrence_lists_by_client_id() -> None:
    base = [{"client_id": "a", "mention_text": "old", "occurrence_order": 0}]
    overlay = [{"client_id": "a", "mention_text": "new", "occurrence_order": 0}]
    merged = merge_occurrence_lists(base, overlay)
    assert len(merged) == 1
    assert merged[0]["mention_text"] == "new"


def test_build_mention_occurrences_overlay_patch() -> None:
    place = {"original_text": "A", "mentions": [{"text": "A"}]}
    patch = {
        "occurrences": [
            {"client_id": "c1", "mention_text": "B", "occurrence_order": 1},
        ]
    }
    out = build_mention_occurrences_for_row(place=place, overlay_patch=patch, db_rows=None)
    assert len(out) == 2
    texts = [o["mention_text"] for o in out]
    assert "A" in texts and "B" in texts
