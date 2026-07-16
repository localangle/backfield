"""Unit tests for strict canonical adjudication result parsing."""

from __future__ import annotations

from worker.substrate.canonical.adjudication_result import (
    adjudication_allows_link,
    parse_canonical_adjudication_result,
)


def test_parse_rejects_link_when_same_identity_false() -> None:
    parsed = parse_canonical_adjudication_result(
        {
            "decision": "link_existing",
            "canonical_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "confidence": 0.99,
            "same_identity": False,
            "conflicting_identity_evidence": True,
            "rationale": "Different people with the same given name",
        },
        candidate_ids={"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
    )
    assert parsed is None


def test_parse_rejects_boolean_confidence() -> None:
    parsed = parse_canonical_adjudication_result(
        {
            "decision": "link_existing",
            "canonical_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "confidence": True,
            "same_identity": True,
            "conflicting_identity_evidence": False,
            "rationale": "ok",
        },
        candidate_ids={"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
    )
    assert parsed is None


def test_parse_rejects_string_confidence() -> None:
    parsed = parse_canonical_adjudication_result(
        {
            "decision": "link_existing",
            "canonical_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "confidence": "0.95",
            "same_identity": True,
            "conflicting_identity_evidence": False,
            "rationale": "ok",
        },
        candidate_ids={"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
    )
    assert parsed is None


def test_parse_accepts_consistent_link() -> None:
    cid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    parsed = parse_canonical_adjudication_result(
        {
            "decision": "link_existing",
            "canonical_id": cid,
            "confidence": 0.95,
            "same_identity": True,
            "conflicting_identity_evidence": False,
            "rationale": "Same person",
        },
        candidate_ids={cid},
    )
    assert parsed is not None
    assert adjudication_allows_link(parsed, min_confidence=0.9) is True


def test_allows_link_requires_confidence_floor() -> None:
    cid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    parsed = parse_canonical_adjudication_result(
        {
            "decision": "link_existing",
            "canonical_id": cid,
            "confidence": 0.8,
            "same_identity": True,
            "conflicting_identity_evidence": False,
            "rationale": "Same person",
        },
        candidate_ids={cid},
    )
    assert parsed is not None
    assert adjudication_allows_link(parsed, min_confidence=0.9) is False
