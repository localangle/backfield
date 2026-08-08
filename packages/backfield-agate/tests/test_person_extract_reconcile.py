"""Tests for cross-chunk person stitching."""

from __future__ import annotations

from agate_nodes.extraction.grounding import ChunkCandidate, GroundedSpan
from agate_nodes.person_extract.reconcile import stitch_people_candidates


def _cand(name: str, start: int, *, owned: bool = True) -> ChunkCandidate[dict]:
    return ChunkCandidate(
        payload={
            "name": name,
            "title": "Mayor" if "Mayor" in name or name == "Joe Smith" else None,
            "mentions": [{"text": name, "quote": False}],
        },
        chunk_index=0,
        evidence=GroundedSpan(start=start, end=start + len(name), text=name),
        owned=owned,
    )


def test_stitches_surname_to_full_name() -> None:
    people, unresolved = stitch_people_candidates(
        [
            _cand("Mayor Joe Smith", 10),
            _cand("Smith", 400),
        ]
    )
    assert unresolved == 0
    assert len(people) == 1
    assert people[0]["name"] in {"Mayor Joe Smith", "Joe Smith"}
    mention_texts = [m["text"] for m in people[0]["mentions"]]
    assert "Smith" in mention_texts


def test_ambiguous_surname_unresolved() -> None:
    people, unresolved = stitch_people_candidates(
        [
            _cand("Joe Smith", 10),
            _cand("Jane Smith", 80),
            _cand("Smith", 400),
        ]
    )
    assert unresolved == 1
    assert len(people) == 2
