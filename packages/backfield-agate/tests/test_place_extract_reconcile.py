"""Tests for place cross-chunk stitching."""

from __future__ import annotations

from agate_nodes.extraction.grounding import ChunkCandidate, GroundedSpan
from agate_nodes.place_extract.reconcile import stitch_place_candidates


def _cand(location: str, start: int, *, place_type: str = "place") -> ChunkCandidate[dict]:
    return ChunkCandidate(
        payload={
            "location": location,
            "type": place_type,
            "components": {"city": "Chicago", "state": "Illinois"},
            "mentions": [{"text": location}],
        },
        chunk_index=0,
        evidence=GroundedSpan(start=start, end=start + len(location), text=location),
        owned=True,
    )


def test_stitches_shortened_venue_name() -> None:
    places, unresolved = stitch_place_candidates(
        [
            _cand("Wrigley Field", 10),
            _cand("Wrigley", 400),
        ]
    )
    assert unresolved == 0
    assert len(places) == 1
    assert places[0]["location"] == "Wrigley Field"
