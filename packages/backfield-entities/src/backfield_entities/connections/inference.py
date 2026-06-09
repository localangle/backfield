"""LLM classification for automatic connection families."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from backfield_entities.connections.caps import MAX_EDGES_RETURNED_PER_FAMILY
from backfield_entities.connections.postprocess import apply_subsumption_rules
from backfield_entities.connections.prompts import build_family_classification_prompt
from backfield_entities.connections.same_site_hints import SameSiteOrgLocationHint
from backfield_entities.connections.same_site_review import review_same_site_org_location_pair
from backfield_entities.connections.snippets import collect_pair_snippets, quote_is_supported
from backfield_entities.connections.taxonomy import AUTO_CONNECTION_PROMPT_VERSION_WITH_HINTS
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
