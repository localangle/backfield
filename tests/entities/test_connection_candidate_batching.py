"""Tests for bounded pair-specific connection classification."""

from __future__ import annotations

import json
import threading
import time
from contextvars import ContextVar

from backfield_entities.connections.inference import classify_candidate_batches
from backfield_entities.connections.types import (
    AutoConnectionCandidatePair,
    LinkedEntitySnapshot,
    PairEvidencePacket,
)


def _candidate(index: int) -> AutoConnectionCandidatePair:
    quote = f"Person {index} works for Organization {index}."
    return AutoConnectionCandidatePair(
        candidate_id=f"candidate-{index}",
        from_entity=LinkedEntitySnapshot(
            entity_type="person",
            substrate_id=index,
            canonical_id=f"person-{index}",
            label=f"Person {index}",
        ),
        to_entity=LinkedEntitySnapshot(
            entity_type="organization",
            substrate_id=index,
            canonical_id=f"org-{index}",
            label=f"Organization {index}",
        ),
        evidence=PairEvidencePacket(
            snippets=(quote,),
            source="same_sentence",
            score=40,
        ),
    )


def _link_decision(
    candidate: AutoConnectionCandidatePair,
    *,
    nature: str = "works_for",
    description: str | None = None,
    quote: str | None = None,
    reason: str = "The article explicitly establishes this relationship.",
) -> dict[str, object]:
    return {
        "candidate_id": candidate.candidate_id,
        "link": True,
        "from_entity_id": candidate.from_entity.canonical_id,
        "to_entity_id": candidate.to_entity.canonical_id,
        "description": description or candidate.evidence.snippets[0],
        "nature": nature,
        "confidence": 0.99,
        "quote": quote or candidate.evidence.snippets[0],
        "reason": reason,
    }


def test_batching_obeys_request_batch_and_concurrency_caps() -> None:
    candidates = tuple(_candidate(index) for index in range(17))
    lock = threading.Lock()
    active = 0
    max_active = 0

    def call_llm(_prompt: str, **_kwargs: object) -> str:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        candidate_ids = [
            line.split("=", 1)[1]
            for line in _prompt.splitlines()
            if line.startswith("- candidate_id=")
        ]
        return json.dumps(
            {
                "decisions": [
                    {
                        "candidate_id": candidate_id,
                        "link": False,
                        "reason": "The evidence does not establish a direct relationship.",
                    }
                    for candidate_id in candidate_ids
                ]
            }
        )

    result = classify_candidate_batches(
        candidates=candidates,
        model="test",
        model_config_id=None,
        call_llm=call_llm,
        max_requests=2,
        batch_size=8,
        concurrency=2,
    )

    assert result.counts.requests == 2
    assert len(result.processed_candidate_ids) == 16
    assert result.overflow_candidate_ids == ("candidate-16",)
    assert max_active == 2


def test_response_must_use_quote_from_its_pair_packet() -> None:
    candidate = _candidate(1)

    def call_llm(_prompt: str, **_kwargs: object) -> str:
        return json.dumps(
            {
                "decisions": [
                    _link_decision(candidate, quote="A quote from some other candidate.")
                ]
            }
        )

    result = classify_candidate_batches(
        candidates=(candidate,),
        model="test",
        model_config_id=None,
        call_llm=call_llm,
        max_requests=1,
    )

    assert result.edges == ()
    assert result.counts.skip_reasons["quote_not_in_pair_evidence"] == 1


def test_one_failed_batch_does_not_discard_other_batches() -> None:
    candidates = tuple(_candidate(index) for index in range(9))

    def call_llm(prompt: str, **_kwargs: object) -> str:
        if "candidate-0" in prompt:
            raise TimeoutError("model timeout")
        return json.dumps(
            {
                "decisions": [
                    {
                        "candidate_id": "candidate-8",
                        "link": False,
                        "reason": "The evidence does not establish a direct relationship.",
                    }
                ]
            }
        )

    result = classify_candidate_batches(
        candidates=candidates,
        model="test",
        model_config_id=None,
        call_llm=call_llm,
        max_requests=2,
        batch_size=8,
        concurrency=2,
    )

    assert result.counts.requests == 2
    assert result.counts.failed_requests == 1
    assert result.processed_candidate_ids == tuple(
        f"candidate-{index}" for index in range(9)
    )


def test_specialized_nature_requires_quote_level_support() -> None:
    candidate = _candidate(1)

    def call_llm(_prompt: str, **_kwargs: object) -> str:
        return json.dumps(
            {
                "decisions": [
                    _link_decision(
                        candidate,
                        nature="leads",
                        description="Person 1 leads Organization 1.",
                    )
                ]
            }
        )

    result = classify_candidate_batches(
        candidates=(candidate,),
        model="test",
        model_config_id=None,
        call_llm=call_llm,
        max_requests=1,
    )

    assert result.edges == ()
    assert result.counts.skip_reasons["nature_not_supported_by_quote"] == 1


def test_model_threads_receive_tracking_context() -> None:
    tracking_value: ContextVar[str | None] = ContextVar("tracking_value", default=None)
    token = tracking_value.set("project-7")
    observed: list[str | None] = []

    def call_llm(_prompt: str, **_kwargs: object) -> str:
        observed.append(tracking_value.get())
        return json.dumps(
            {
                "decisions": [
                    {
                        "candidate_id": "candidate-1",
                        "link": False,
                        "reason": "The evidence does not establish a direct relationship.",
                    }
                ]
            }
        )

    try:
        classify_candidate_batches(
            candidates=(_candidate(1),),
            model="test",
            model_config_id=None,
            call_llm=call_llm,
            max_requests=1,
        )
    finally:
        tracking_value.reset(token)

    assert observed == ["project-7"]


def test_model_decline_is_authoritative() -> None:
    candidate = _candidate(1)

    def call_llm(_prompt: str, **_kwargs: object) -> str:
        return json.dumps(
            {
                "decisions": [
                    {
                        "candidate_id": candidate.candidate_id,
                        "link": False,
                        "from_entity_id": "person-1",
                        "to_entity_id": "org-1",
                        "description": "Explicit organizational leadership link",
                        "nature": "board_member_of",
                        "confidence": 0.92,
                        "quote": candidate.evidence.snippets[0],
                        "reason": (
                            "The article references the organization but does not establish "
                            "a direct board membership or leadership role."
                        ),
                    }
                ]
            }
        )

    result = classify_candidate_batches(
        candidates=(candidate,),
        model="test",
        model_config_id=None,
        call_llm=call_llm,
        max_requests=1,
    )

    assert result.edges == ()
    assert result.counts.skip_reasons["model_declined"] == 1


def test_affirmative_decision_with_declining_reason_is_rejected() -> None:
    candidate = _candidate(1)

    def call_llm(_prompt: str, **_kwargs: object) -> str:
        return json.dumps(
            {
                "decisions": [
                    _link_decision(
                        candidate,
                        reason=(
                            "The article mentions both entities but does not establish "
                            "a direct relationship."
                        ),
                    )
                ]
            }
        )

    result = classify_candidate_batches(
        candidates=(candidate,),
        model="test",
        model_config_id=None,
        call_llm=call_llm,
        max_requests=1,
    )

    assert result.edges == ()
    assert result.counts.skip_reasons["judgment_declines"] == 1
