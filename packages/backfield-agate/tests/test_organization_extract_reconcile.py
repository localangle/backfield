"""Tests for organization cross-chunk stitching."""

from __future__ import annotations

from agate_nodes.extraction.grounding import ChunkCandidate, GroundedSpan
from agate_nodes.organization_extract.reconcile import stitch_organization_candidates


def _cand(name: str, start: int) -> ChunkCandidate[dict]:
    return ChunkCandidate(
        payload={"name": name, "mentions": [{"text": name, "quote": False}]},
        chunk_index=0,
        evidence=GroundedSpan(start=start, end=start + len(name), text=name),
        owned=True,
    )


def test_stitches_acronym_to_expanded_name() -> None:
    orgs, unresolved = stitch_organization_candidates(
        [
            _cand("Chicago Public Schools", 10),
            _cand("CPS", 300),
        ]
    )
    assert unresolved == 0
    assert len(orgs) == 1
    assert orgs[0]["name"] == "Chicago Public Schools"
