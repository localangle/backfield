"""LLM classification for automatic connection families."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import copy_context
from dataclasses import dataclass, field
from datetime import datetime

from backfield_entities.connections.candidate_pairs import (
    explicit_person_represents_party_district_evidence,
)
from backfield_entities.connections.caps import (
    MAX_CANDIDATE_PAIRS_PER_BATCH,
    MAX_CONNECTION_REQUEST_CONCURRENCY,
)
from backfield_entities.connections.match_tokens import (
    org_location_site_names_match,
    person_affiliation_matches_organization_label,
)
from backfield_entities.connections.natures import nature_def
from backfield_entities.connections.prompts import build_candidate_batch_prompt
from backfield_entities.connections.taxonomy import AUTO_CONNECTION_PROMPT_VERSION_EVIDENCE_PAIRS
from backfield_entities.connections.types import (
    AutoConnectionCandidateDecision,
    AutoConnectionCandidatePair,
    AutoConnectionEdgeProposal,
)
from backfield_entities.connections.validation import validate_auto_connection_candidate

logger = logging.getLogger(__name__)


@dataclass
class FamilyInferenceCounts:
    proposed: int = 0
    accepted: int = 0
    skipped: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class FamilyInferenceResult:
    from_entity_type: str
    to_entity_type: str
    edges: tuple[AutoConnectionEdgeProposal, ...]
    counts: FamilyInferenceCounts


@dataclass
class CandidateBatchInferenceCounts:
    requests: int = 0
    failed_requests: int = 0
    prompt_characters: int = 0
    malformed_proposals: int = 0
    proposed: int = 0
    accepted: int = 0
    skipped: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0


@dataclass(frozen=True)
class CandidateBatchInferenceResult:
    edges: tuple[AutoConnectionEdgeProposal, ...]
    processed_candidate_ids: tuple[str, ...]
    overflow_candidate_ids: tuple[str, ...]
    counts: CandidateBatchInferenceCounts


def _candidate_chunks(
    candidates: tuple[AutoConnectionCandidatePair, ...],
    size: int,
) -> list[tuple[AutoConnectionCandidatePair, ...]]:
    return [candidates[index : index + size] for index in range(0, len(candidates), size)]


def _record_candidate_skip(
    counts: CandidateBatchInferenceCounts,
    reason: str,
) -> None:
    counts.skipped += 1
    counts.skip_reasons[reason] = counts.skip_reasons.get(reason, 0) + 1


def _candidate_for_proposal(
    proposal: AutoConnectionEdgeProposal,
    batch: tuple[AutoConnectionCandidatePair, ...],
) -> AutoConnectionCandidatePair | None:
    by_id = {candidate.candidate_id: candidate for candidate in batch}
    if proposal.candidate_id:
        return by_id.get(proposal.candidate_id)
    # Compatibility for older model responses: endpoint matching is still pair-bound.
    matches = [
        candidate
        for candidate in batch
        if {
            candidate.from_entity.canonical_id,
            candidate.to_entity.canonical_id,
        }
        == {proposal.from_entity_id, proposal.to_entity_id}
    ]
    return matches[0] if len(matches) == 1 else None


def _proposal_matches_candidate(
    proposal: AutoConnectionEdgeProposal,
    candidate: AutoConnectionCandidatePair,
) -> bool:
    candidate_ids = {
        candidate.from_entity.canonical_id,
        candidate.to_entity.canonical_id,
    }
    proposal_ids = {proposal.from_entity_id, proposal.to_entity_id}
    if candidate_ids != proposal_ids:
        return False
    if candidate.from_entity_type == candidate.to_entity_type:
        return True
    return (
        proposal.from_entity_id == candidate.from_entity.canonical_id
        and proposal.to_entity_id == candidate.to_entity.canonical_id
    )


def _quote_in_candidate_evidence(
    quote: str,
    candidate: AutoConnectionCandidatePair,
) -> bool:
    text = quote.strip()
    return bool(text) and any(text in snippet for snippet in candidate.evidence.snippets)


_DECLINING_JUDGMENT_PATTERNS = (
    r"\bdoes not (?:explicitly |directly )?"
    r"(?:establish|show|indicate|support|demonstrate|confirm|prove)\b",
    r"\b(?:cannot|can't) (?:establish|infer|confirm|conclude|support)\b",
    r"\b(?:no|insufficient|not enough) (?:direct |clear |explicit )?evidence\b",
    r"\b(?:no|not a) (?:direct )?(?:relationship|connection|link)\b",
    r"\b(?:relationship|connection|link) (?:is|was) not established\b",
    r"\b(?:only|merely) (?:a )?co[- ]?mention\b",
)


def _reason_declines_link(reason: str) -> bool:
    text = reason.strip().casefold()
    return any(re.search(pattern, text) for pattern in _DECLINING_JUDGMENT_PATTERNS)


def _quote_supports_specialized_nature(
    quote: str,
    nature: str | None,
    candidate: AutoConnectionCandidatePair,
) -> bool:
    text = quote.strip().casefold()
    if len(text) < 15:
        return False
    if nature in {"coaches", "plays_for"}:
        if (
            candidate.from_entity_type == "person"
            and candidate.to_entity_type == "organization"
            and person_affiliation_matches_organization_label(
                candidate.from_entity.affiliation,
                candidate.to_entity.label,
            )
        ):
            return True
        return False
    if nature == "leads":
        if "coach" in text and not re.search(
            r"\b(president|chief|ceo|director|executive|chair|founder|owner)\b",
            text,
        ):
            return False
        return bool(
            re.search(
                r"\b(leads?|led|president|chief|ceo|director|executive|chair|"
                r"founder|owner|head of)\b",
                text,
            )
        )
    if nature == "located_at":
        if (
            candidate.from_entity_type == "organization"
            and candidate.to_entity_type == "location"
            and org_location_site_names_match(
                candidate.from_entity.label,
                candidate.to_entity.label,
            )[0]
        ):
            return True
        return bool(
            re.search(
                r"\b(located|headquartered|based|office|campus|facility|address|"
                r"(?:is|are|sits|stands) at)\b",
                text,
            )
        )
    if nature == "represents":
        party_district = explicit_person_represents_party_district_evidence(candidate)
        if party_district is not None:
            return True
    if nature == "holds_office_in":
        return bool(
            re.search(
                r"\b(mayor|governor|sheriff|attorney general|officeholder|"
                r"city council|alder(?:man|woman|person))\b",
                text,
            )
        )
    if nature == "studied_at":
        return bool(
            re.search(
                r"\b(studied|attended|graduated|graduate of|alumnus|alumna|"
                r"earned (?:a|an|his|her|their) degree)\b",
                text,
            )
        )
    return True


def _validate_candidate_batch_response(
    raw: str,
    *,
    batch: tuple[AutoConnectionCandidatePair, ...],
    counts: CandidateBatchInferenceCounts,
) -> list[AutoConnectionEdgeProposal]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        _record_candidate_skip(counts, "invalid_llm_json")
        return []
    rows = payload.get("decisions") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        _record_candidate_skip(counts, "invalid_llm_json")
        return []

    accepted: list[AutoConnectionEdgeProposal] = []
    candidate_by_id = {candidate.candidate_id: candidate for candidate in batch}
    seen_candidate_ids: set[str] = set()
    decided_candidate_ids: set[str] = set()
    for row in rows:
        try:
            decision = AutoConnectionCandidateDecision.model_validate(row)
        except Exception:
            counts.malformed_proposals += 1
            _record_candidate_skip(counts, "malformed_decision")
            continue
        counts.proposed += 1
        if decision.candidate_id in seen_candidate_ids:
            _record_candidate_skip(counts, "duplicate_model_decision")
            continue
        seen_candidate_ids.add(decision.candidate_id)
        candidate = candidate_by_id.get(decision.candidate_id)
        if candidate is None:
            _record_candidate_skip(counts, "invalid_candidate_id")
            continue
        decided_candidate_ids.add(decision.candidate_id)
        if not decision.link:
            _record_candidate_skip(counts, "model_declined")
            continue
        if _reason_declines_link(decision.reason):
            _record_candidate_skip(counts, "judgment_declines")
            continue
        try:
            proposal = AutoConnectionEdgeProposal.model_validate(
                decision.model_dump(exclude={"link"})
            )
        except Exception:
            counts.malformed_proposals += 1
            _record_candidate_skip(counts, "malformed_link_decision")
            continue
        candidate = _candidate_for_proposal(proposal, batch)
        assert candidate is not None
        if not _proposal_matches_candidate(proposal, candidate):
            _record_candidate_skip(counts, "candidate_endpoint_mismatch")
            continue
        if proposal.from_entity_id == proposal.to_entity_id:
            _record_candidate_skip(counts, "self_loop")
            continue
        if not _quote_in_candidate_evidence(proposal.quote, candidate):
            _record_candidate_skip(counts, "quote_not_in_pair_evidence")
            continue
        if proposal.nature is None:
            _record_candidate_skip(counts, "missing_supported_nature")
            continue
        if not _quote_supports_specialized_nature(
            proposal.quote,
            proposal.nature,
            candidate,
        ):
            _record_candidate_skip(counts, "nature_not_supported_by_quote")
            continue

        from_entity = candidate.from_entity
        to_entity = candidate.to_entity
        if proposal.from_entity_id != from_entity.canonical_id:
            from_entity, to_entity = to_entity, from_entity
        location_type = (
            to_entity.location_type if to_entity.entity_type == "location" else None
        )
        validation = validate_auto_connection_candidate(
            from_entity_type=from_entity.entity_type,
            to_entity_type=to_entity.entity_type,
            description=proposal.description,
            nature=proposal.nature,
            confidence=float(proposal.confidence),
            quote=proposal.quote,
            location_type=location_type,
        )
        if not validation.ok:
            _record_candidate_skip(
                counts,
                validation.skip_reason or "validation_failed",
            )
            continue
        definition = nature_def(
            proposal.nature,
            from_entity.entity_type,
            to_entity.entity_type,
        )
        asserted_currentness = proposal.asserted_currentness
        if definition is not None and definition.temporal_kind == "static":
            asserted_currentness = "unspecified"
        accepted.append(
            proposal.model_copy(
                update={
                    "candidate_id": candidate.candidate_id,
                    "match_basis": proposal.match_basis
                    or candidate.evidence.match_basis,
                    "prompt_version": proposal.prompt_version
                    or AUTO_CONNECTION_PROMPT_VERSION_EVIDENCE_PAIRS,
                    "asserted_currentness": asserted_currentness,
                    "currentness_review_source": "llm",
                }
            )
        )
        counts.accepted += 1
    missing_decisions = len(candidate_by_id.keys() - decided_candidate_ids)
    for _ in range(missing_decisions):
        _record_candidate_skip(counts, "missing_model_decision")
    return accepted


def classify_candidate_batches(
    *,
    candidates: tuple[AutoConnectionCandidatePair, ...],
    model: str,
    model_config_id: str | None,
    call_llm: Callable[..., str],
    max_requests: int,
    reference_at: datetime | None = None,
    batch_size: int = MAX_CANDIDATE_PAIRS_PER_BATCH,
    concurrency: int = MAX_CONNECTION_REQUEST_CONCURRENCY,
) -> CandidateBatchInferenceResult:
    """Classify bounded pair-specific batches with model calls only in worker threads."""
    counts = CandidateBatchInferenceCounts()
    if not candidates or max_requests <= 0:
        return CandidateBatchInferenceResult(
            edges=(),
            processed_candidate_ids=(),
            overflow_candidate_ids=tuple(candidate.candidate_id for candidate in candidates),
            counts=counts,
        )

    all_chunks = _candidate_chunks(candidates, max(1, batch_size))
    selected_chunks = all_chunks[:max_requests]
    overflow = tuple(
        candidate.candidate_id
        for chunk in all_chunks[max_requests:]
        for candidate in chunk
    )
    prompts = [
        (
            chunk,
            build_candidate_batch_prompt(chunk, reference_at=reference_at),
        )
        for chunk in selected_chunks
    ]
    counts.requests = len(prompts)
    counts.prompt_characters = sum(len(prompt) for _, prompt in prompts)
    started = time.monotonic()

    def _call(prompt: str) -> str:
        return call_llm(
            prompt,
            model=model,
            force_json=True,
            temperature=0.0,
            model_config_id=model_config_id,
        )

    responses: dict[int, str | None] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, len(prompts)))) as executor:
        futures = {
            executor.submit(copy_context().run, _call, prompt): index
            for index, (_, prompt) in enumerate(prompts)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                responses[index] = future.result()
            except Exception as exc:
                logger.warning("Auto-connection candidate batch failed: %s", exc)
                responses[index] = None
                counts.failed_requests += 1
                _record_candidate_skip(counts, "llm_error")

    accepted: list[AutoConnectionEdgeProposal] = []
    for index, (batch, _prompt) in enumerate(prompts):
        raw = responses.get(index)
        if raw is None:
            continue
        accepted.extend(
            _validate_candidate_batch_response(raw, batch=batch, counts=counts)
        )
    counts.elapsed_seconds = time.monotonic() - started
    processed = tuple(
        candidate.candidate_id for chunk in selected_chunks for candidate in chunk
    )
    return CandidateBatchInferenceResult(
        edges=tuple(accepted),
        processed_candidate_ids=processed,
        overflow_candidate_ids=overflow,
        counts=counts,
    )
