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

from backfield_entities.connections.candidate_pairs import (
    explicit_person_org_nature_evidence,
)
from backfield_entities.connections.caps import (
    MAX_CANDIDATE_PAIRS_PER_BATCH,
    MAX_CONNECTION_REQUEST_CONCURRENCY,
    MAX_EDGES_RETURNED_PER_FAMILY,
)
from backfield_entities.connections.postprocess import apply_subsumption_rules
from backfield_entities.connections.prompts import (
    build_candidate_batch_prompt,
    build_family_classification_prompt,
)
from backfield_entities.connections.same_site_hints import SameSiteOrgLocationHint
from backfield_entities.connections.same_site_review import review_same_site_org_location_pair
from backfield_entities.connections.snippets import collect_pair_snippets, quote_is_supported
from backfield_entities.connections.taxonomy import (
    AUTO_CONNECTION_PROMPT_VERSION_EVIDENCE_PAIRS,
    AUTO_CONNECTION_PROMPT_VERSION_WITH_HINTS,
)
from backfield_entities.connections.types import (
    AutoConnectionCandidateDecision,
    AutoConnectionCandidatePair,
    AutoConnectionEdgeProposal,
    AutoConnectionFamilyResponse,
    LinkedEntitySnapshot,
)
from backfield_entities.connections.validation import validate_auto_connection_candidate

logger = logging.getLogger(__name__)

AUTO_CONNECTION_FAMILIES: tuple[tuple[str, str], ...] = (
    ("person", "organization"),
    ("organization", "location"),
    ("person", "location"),
    ("person", "person"),
    ("organization", "organization"),
)


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


def _record_skip(counts: FamilyInferenceCounts, reason: str) -> None:
    counts.skipped += 1
    counts.skip_reasons[reason] = counts.skip_reasons.get(reason, 0) + 1


def _entities_by_id(
    entities: tuple[LinkedEntitySnapshot, ...],
) -> dict[str, LinkedEntitySnapshot]:
    return {entity.canonical_id: entity for entity in entities}


def _parse_family_response(raw: str) -> AutoConnectionFamilyResponse | None:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    try:
        return AutoConnectionFamilyResponse.model_validate(data)
    except Exception:
        return None


def _hint_by_pair(
    hints: tuple[SameSiteOrgLocationHint, ...],
) -> dict[tuple[str, str], SameSiteOrgLocationHint]:
    return {(hint.org.canonical_id, hint.location.canonical_id): hint for hint in hints}


def _apply_hint_metadata(
    edges: list[AutoConnectionEdgeProposal],
    *,
    hints: tuple[SameSiteOrgLocationHint, ...],
    family_prompt_version: str | None = None,
) -> list[AutoConnectionEdgeProposal]:
    if not hints:
        return edges
    hint_map = _hint_by_pair(hints)
    updated: list[AutoConnectionEdgeProposal] = []
    for edge in edges:
        hint = hint_map.get((edge.from_entity_id, edge.to_entity_id))
        if hint is None:
            updated.append(edge)
            continue
        updated.append(
            edge.model_copy(
                update={
                    "match_basis": edge.match_basis or hint.match_basis,
                    "prompt_version": edge.prompt_version or family_prompt_version,
                }
            )
        )
    return updated


def _filter_valid_edges(
    *,
    from_entity_type: str,
    to_entity_type: str,
    from_entities: tuple[LinkedEntitySnapshot, ...],
    to_entities: tuple[LinkedEntitySnapshot, ...],
    proposals: list[AutoConnectionEdgeProposal],
    article_text: str,
    pair_snippets: tuple[str, ...],
    counts: FamilyInferenceCounts,
) -> list[AutoConnectionEdgeProposal]:
    from_by_id = _entities_by_id(from_entities)
    to_by_id = _entities_by_id(to_entities)
    accepted: list[AutoConnectionEdgeProposal] = []

    for proposal in proposals[:MAX_EDGES_RETURNED_PER_FAMILY]:
        counts.proposed += 1
        from_entity = from_by_id.get(proposal.from_entity_id)
        to_entity = to_by_id.get(proposal.to_entity_id)
        if from_entity is None or to_entity is None:
            _record_skip(counts, "invalid_entity_id")
            continue

        if not quote_is_supported(
            proposal.quote,
            article_text=article_text,
            from_entity=from_entity,
            to_entity=to_entity,
            pair_snippets=pair_snippets,
        ):
            _record_skip(counts, "quote_not_supported")
            continue

        location_type = to_entity.location_type if to_entity_type == "location" else None
        validation = validate_auto_connection_candidate(
            from_entity_type=from_entity_type,
            to_entity_type=to_entity_type,
            description=proposal.description,
            nature=proposal.nature,
            confidence=float(proposal.confidence),
            quote=proposal.quote,
            location_type=location_type,
        )
        if not validation.ok:
            _record_skip(counts, validation.skip_reason or "validation_failed")
            continue

        accepted.append(proposal)
        counts.accepted += 1

    return apply_subsumption_rules(accepted)


def _review_unresolved_same_site_hints(
    *,
    hints: tuple[SameSiteOrgLocationHint, ...],
    accepted_edges: list[AutoConnectionEdgeProposal],
    from_entities: tuple[LinkedEntitySnapshot, ...],
    to_entities: tuple[LinkedEntitySnapshot, ...],
    article_text: str,
    pair_snippets: tuple[str, ...],
    model: str,
    model_config_id: str | None,
    call_llm: Callable[..., str],
    counts: FamilyInferenceCounts,
) -> list[AutoConnectionEdgeProposal]:
    if not hints:
        return accepted_edges

    accepted_keys = {(edge.from_entity_id, edge.to_entity_id) for edge in accepted_edges}
    extra: list[AutoConnectionEdgeProposal] = []

    for hint in hints:
        key = (hint.org.canonical_id, hint.location.canonical_id)
        if key in accepted_keys:
            continue
        proposal = review_same_site_org_location_pair(
            hint=hint,
            article_text=article_text,
            model=model,
            model_config_id=model_config_id,
            call_llm=call_llm,
        )
        if proposal is None:
            continue
        validated = _filter_valid_edges(
            from_entity_type="organization",
            to_entity_type="location",
            from_entities=from_entities,
            to_entities=to_entities,
            proposals=[proposal],
            article_text=article_text,
            pair_snippets=pair_snippets,
            counts=counts,
        )
        if validated:
            extra.extend(validated)
            accepted_keys.add(key)

    if not extra:
        return accepted_edges
    return apply_subsumption_rules([*accepted_edges, *extra])


def classify_connection_family(
    *,
    from_entity_type: str,
    to_entity_type: str,
    from_entities: tuple[LinkedEntitySnapshot, ...],
    to_entities: tuple[LinkedEntitySnapshot, ...],
    article_text: str,
    model: str,
    model_config_id: str | None,
    call_llm: Callable[..., str],
    same_site_hints: tuple[SameSiteOrgLocationHint, ...] = (),
) -> FamilyInferenceResult:
    """Run one endpoint-family LLM classification pass."""
    counts = FamilyInferenceCounts()
    if not from_entities or not to_entities:
        return FamilyInferenceResult(
            from_entity_type=from_entity_type,
            to_entity_type=to_entity_type,
            edges=(),
            counts=counts,
        )

    extra_snippets = tuple(
        snippet
        for hint in same_site_hints
        for snippet in hint.suggested_snippets
    )
    pair_snippets = collect_pair_snippets(
        from_entities=from_entities,
        to_entities=to_entities,
        article_text=article_text,
        extra_snippets=extra_snippets,
    )
    family_prompt_version = (
        AUTO_CONNECTION_PROMPT_VERSION_WITH_HINTS if same_site_hints else None
    )
    prompt = build_family_classification_prompt(
        from_type=from_entity_type,
        to_type=to_entity_type,
        from_entities=from_entities,
        to_entities=to_entities,
        pair_snippets=pair_snippets,
        same_site_hints=same_site_hints,
    )
    try:
        raw = call_llm(
            prompt,
            model=model,
            force_json=True,
            temperature=0.0,
            model_config_id=model_config_id,
        )
    except Exception as exc:
        logger.warning(
            "Auto-connection LLM failed for %s -> %s: %s",
            from_entity_type,
            to_entity_type,
            exc,
        )
        _record_skip(counts, "llm_error")
        return FamilyInferenceResult(
            from_entity_type=from_entity_type,
            to_entity_type=to_entity_type,
            edges=(),
            counts=counts,
        )

    parsed = _parse_family_response(raw)
    if parsed is None:
        _record_skip(counts, "invalid_llm_json")
        accepted_edges: list[AutoConnectionEdgeProposal] = []
    else:
        accepted_edges = _filter_valid_edges(
            from_entity_type=from_entity_type,
            to_entity_type=to_entity_type,
            from_entities=from_entities,
            to_entities=to_entities,
            proposals=list(parsed.edges),
            article_text=article_text,
            pair_snippets=pair_snippets,
            counts=counts,
        )

    accepted_edges = _apply_hint_metadata(
        accepted_edges,
        hints=same_site_hints,
        family_prompt_version=family_prompt_version,
    )

    if (
        from_entity_type == "organization"
        and to_entity_type == "location"
        and same_site_hints
    ):
        accepted_edges = _review_unresolved_same_site_hints(
            hints=same_site_hints,
            accepted_edges=accepted_edges,
            from_entities=from_entities,
            to_entities=to_entities,
            article_text=article_text,
            pair_snippets=pair_snippets,
            model=model,
            model_config_id=model_config_id,
            call_llm=call_llm,
            counts=counts,
        )

    return FamilyInferenceResult(
        from_entity_type=from_entity_type,
        to_entity_type=to_entity_type,
        edges=tuple(accepted_edges),
        counts=counts,
    )


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
        explicit = explicit_person_org_nature_evidence(candidate)
        return explicit is not None and explicit[0] == nature
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
        return bool(
            re.search(
                r"\b(located|headquartered|based|office|campus|facility|address|"
                r"(?:is|are|sits|stands) at)\b",
                text,
            )
        )
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
        accepted.append(
            proposal.model_copy(
                update={
                    "candidate_id": candidate.candidate_id,
                    "match_basis": proposal.match_basis
                    or candidate.evidence.match_basis,
                    "prompt_version": proposal.prompt_version
                    or AUTO_CONNECTION_PROMPT_VERSION_EVIDENCE_PAIRS,
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
    prompts = [(chunk, build_candidate_batch_prompt(chunk)) for chunk in selected_chunks]
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
