"""LLM classification for automatic connection families."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from backfield_entities.connections.caps import MAX_EDGES_RETURNED_PER_FAMILY
from backfield_entities.connections.postprocess import apply_subsumption_rules
from backfield_entities.connections.prompts import build_family_classification_prompt
from backfield_entities.connections.snippets import collect_pair_snippets, quote_is_supported
from backfield_entities.connections.types import (
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

    pair_snippets = collect_pair_snippets(
        from_entities=from_entities,
        to_entities=to_entities,
        article_text=article_text,
    )
    prompt = build_family_classification_prompt(
        from_type=from_entity_type,
        to_type=to_entity_type,
        from_entities=from_entities,
        to_entities=to_entities,
        pair_snippets=pair_snippets,
    )
    try:
        raw = call_llm(
            prompt,
            model=model,
            force_json=True,
            temperature=0.0,
            max_tokens=1200,
            model_config_id=model_config_id,
        )
    except Exception as exc:
        logger.warning(
            "Auto-connection LLM failed for %s -> %s: %s",
            from_entity_type,
            to_entity_type,
            exc,
            exc_info=True,
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
        return FamilyInferenceResult(
            from_entity_type=from_entity_type,
            to_entity_type=to_entity_type,
            edges=(),
            counts=counts,
        )

    edges = _filter_valid_edges(
        from_entity_type=from_entity_type,
        to_entity_type=to_entity_type,
        from_entities=from_entities,
        to_entities=to_entities,
        proposals=list(parsed.edges),
        article_text=article_text,
        pair_snippets=pair_snippets,
        counts=counts,
    )
    return FamilyInferenceResult(
        from_entity_type=from_entity_type,
        to_entity_type=to_entity_type,
        edges=tuple(edges),
        counts=counts,
    )
