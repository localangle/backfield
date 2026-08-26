"""Backfield Output integration for automatic connection inference."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from sqlmodel import Session

from backfield_entities.connections.affiliation_links import (
    infer_affiliation_person_organization_edges,
)
from backfield_entities.connections.candidate_pairs import (
    AUTO_CONNECTION_FAMILIES,
    build_deterministic_connection_proposals,
    generate_connection_candidates,
)
from backfield_entities.connections.caps import (
    MAX_CANDIDATE_PAIRS_PER_ARTICLE,
    MAX_CANDIDATE_PAIRS_PER_BATCH,
    MAX_CREATED_EDGES_PER_ITEM,
    MAX_TOTAL_CONNECTION_REQUESTS,
)
from backfield_entities.connections.context import (
    AutoConnectionArticleContext,
    collect_auto_connection_article_context,
)
from backfield_entities.connections.eligibility import evaluate_auto_connections_eligibility
from backfield_entities.connections.inference import (
    CandidateBatchInferenceResult,
    FamilyInferenceCounts,
    FamilyInferenceResult,
    classify_candidate_batches,
)
from backfield_entities.connections.postprocess import resolve_auto_connection_proposals
from backfield_entities.connections.same_site_links import (
    infer_same_site_org_location_edges,
)
from backfield_entities.connections.summary import build_auto_connections_summary
from backfield_entities.connections.types import (
    AutoConnectionCandidatePair,
    AutoConnectionEdgeProposal,
    LinkedEntitySnapshot,
)
from backfield_entities.connections.writer import (
    AutoConnectionWriteResult,
    write_auto_connections,
)
from backfield_entities.ingest.db_output_settings import DbOutputCanonicalSettings

logger = logging.getLogger(__name__)


def _family_entities(
    context: AutoConnectionArticleContext,
    *,
    from_entity_type: str,
    to_entity_type: str,
) -> tuple[tuple[LinkedEntitySnapshot, ...], tuple[LinkedEntitySnapshot, ...]]:
    by_type = {
        "person": context.people,
        "organization": context.organizations,
        "location": context.locations,
    }
    return by_type[from_entity_type], by_type[to_entity_type]


def _family_results_from_candidates(
    context: AutoConnectionArticleContext,
    inference: CandidateBatchInferenceResult,
    candidate_family_by_id: dict[str, tuple[str, str]],
    accepted_edges: tuple[AutoConnectionEdgeProposal, ...],
) -> list[FamilyInferenceResult]:
    edges_by_family: dict[tuple[str, str], list[AutoConnectionEdgeProposal]] = defaultdict(list)
    for edge in accepted_edges:
        family = candidate_family_by_id.get(edge.candidate_id or "")
        if family is not None:
            edges_by_family[family].append(edge)

    results: list[FamilyInferenceResult] = []
    first = True
    for from_type, to_type in AUTO_CONNECTION_FAMILIES:
        from_entities, to_entities = _family_entities(
            context,
            from_entity_type=from_type,
            to_entity_type=to_type,
        )
        if not from_entities or not to_entities:
            continue
        edges = edges_by_family.get((from_type, to_type), [])
        counts = FamilyInferenceCounts(
            proposed=len(edges),
            accepted=len(edges),
        )
        if first:
            counts.proposed += inference.counts.skipped
            counts.skipped = inference.counts.skipped
            counts.skip_reasons = dict(inference.counts.skip_reasons)
            first = False
        results.append(
            FamilyInferenceResult(
                from_entity_type=from_type,
                to_entity_type=to_type,
                edges=tuple(edges),
                counts=counts,
            )
        )
    return results


def _merge_write_results(
    target: AutoConnectionWriteResult,
    source: AutoConnectionWriteResult,
) -> None:
    target.created.extend(source.created)
    target.reinforced.extend(source.reinforced)
    target.skipped_existing_count += source.skipped_existing_count


def _endpoint_family_for_proposal(
    edge: AutoConnectionEdgeProposal,
    candidate_by_id: dict[str, AutoConnectionCandidatePair],
) -> tuple[str, str] | None:
    candidate = candidate_by_id.get(edge.candidate_id or "")
    if candidate is not None:
        return candidate.from_entity_type, candidate.to_entity_type
    if edge.match_basis == "affiliation_match":
        return "person", "organization"
    if edge.match_basis in {"site_name_exact", "org_at_named_place"}:
        return "organization", "location"
    if edge.match_basis == "explicit_party_district_construction":
        return "person", "location"
    return None


def run_auto_connections_for_db_output(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    article_text: str,
    settings: DbOutputCanonicalSettings,
    run_id: str | None = None,
    processed_item_id: int | None = None,
    call_llm: Callable[..., str],
    candidate_ids: tuple[str, ...] | None = None,
    max_requests: int = MAX_TOTAL_CONNECTION_REQUESTS,
    defer_overflow: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Infer and persist high-confidence connections after substrate persistence."""
    eligibility = evaluate_auto_connections_eligibility(settings)
    if not eligibility.enabled:
        return build_auto_connections_summary(
            enabled=False,
            eligible=False,
            reason=eligibility.reason,
        )
    if not eligibility.eligible:
        return build_auto_connections_summary(
            enabled=True,
            eligible=False,
            reason=eligibility.reason,
        )

    model = settings.adjudication_model.strip() or "gpt-5-nano"
    model_config_id = settings.adjudication_ai_model_config_id

    try:
        context = collect_auto_connection_article_context(
            session,
            project_id=project_id,
            article_id=article_id,
            article_text=article_text,
        )
        # Release the persist transaction before LLM classification (can take tens of seconds).
        session.commit()
        generation = generate_connection_candidates(
            people=context.people,
            organizations=context.organizations,
            locations=context.locations,
            article_text=context.article_text,
            limit=MAX_CANDIDATE_PAIRS_PER_ARTICLE,
        )
        selected_candidates = generation.candidates
        if candidate_ids is not None:
            selected = set(candidate_ids)
            selected_candidates = tuple(
                candidate
                for candidate in generation.candidates
                if candidate.candidate_id in selected
            )
        inference = classify_candidate_batches(
            candidates=selected_candidates,
            model=model,
            model_config_id=model_config_id,
            call_llm=call_llm,
            max_requests=max_requests,
        )
        candidate_by_id = {
            candidate.candidate_id: candidate for candidate in selected_candidates
        }
        candidate_family_by_id = {
            candidate.candidate_id: (
                candidate.from_entity_type,
                candidate.to_entity_type,
            )
            for candidate in selected_candidates
        }
        affiliation_edges = infer_affiliation_person_organization_edges(
            people=context.people,
            organizations=context.organizations,
            article_text=context.article_text,
        )
        same_site_edges = infer_same_site_org_location_edges(
            organizations=context.organizations,
            locations=context.locations,
            article_text=context.article_text,
        )
        deterministic_edges = build_deterministic_connection_proposals(
            selected_candidates
        )
        all_proposals = (
            *affiliation_edges,
            *same_site_edges,
            *deterministic_edges,
            *inference.edges,
        )
        resolution = resolve_auto_connection_proposals(
            list(all_proposals),
            candidates=candidate_by_id,
        )
        resolved_edges = list(resolution.edges)
        created_cap_skipped = 0
        if len(resolved_edges) > MAX_CREATED_EDGES_PER_ITEM:
            created_cap_skipped = len(resolved_edges) - MAX_CREATED_EDGES_PER_ITEM
            resolved_edges = resolved_edges[:MAX_CREATED_EDGES_PER_ITEM]

        write_result = AutoConnectionWriteResult()
        edges_by_family: dict[
            tuple[str, str],
            list[AutoConnectionEdgeProposal],
        ] = defaultdict(list)
        for edge in resolved_edges:
            family = _endpoint_family_for_proposal(edge, candidate_by_id)
            if family is None:
                continue
            edges_by_family[family].append(edge)

        for (from_type, to_type), edges in edges_by_family.items():
            if dry_run:
                continue
            from_entities, to_entities = _family_entities(
                context,
                from_entity_type=from_type,
                to_entity_type=to_type,
            )
            batch = write_auto_connections(
                session,
                project_id=project_id,
                from_entity_type=from_type,
                to_entity_type=to_type,
                from_entities=from_entities,
                to_entities=to_entities,
                edges=edges,
                article_id=article_id,
                run_id=run_id,
                processed_item_id=processed_item_id,
                adjudication_model=model,
                adjudication_ai_model_config_id=model_config_id,
            )
            _merge_write_results(write_result, batch)

        family_results = _family_results_from_candidates(
            context,
            inference,
            candidate_family_by_id,
            all_proposals,
        )
        diagnostics = {
            "candidate_pairs_considered": generation.stats.considered,
            "candidate_pairs_generated": generation.stats.generated,
            "candidate_pairs_rejected_no_evidence": generation.stats.rejected_no_evidence,
            "candidate_pairs_truncated": generation.stats.truncated,
            "candidate_sources": dict(generation.stats.by_source),
            "linked_entities": dict(context.entity_counts),
            "linked_entities_truncated": dict(context.entity_truncated),
            "requests": inference.counts.requests,
            "failed_requests": inference.counts.failed_requests,
            "prompt_characters": inference.counts.prompt_characters,
            "malformed_proposals": inference.counts.malformed_proposals,
            "deterministic_proposals": len(deterministic_edges),
            "affiliation_proposals": len(affiliation_edges),
            "same_site_proposals": len(same_site_edges),
            "elapsed_seconds": round(inference.counts.elapsed_seconds, 3),
            "exact_duplicates": resolution.stats.exact_duplicates,
            "subsumed": resolution.stats.subsumed,
            "conflicts_resolved": resolution.stats.conflicts_resolved,
            "ambiguous_conflicts": resolution.stats.ambiguous_conflicts,
            "self_loops": resolution.stats.self_loops,
            "selected_candidate_pairs": len(inference.processed_candidate_ids),
            "deferred_candidate_pairs": len(inference.overflow_candidate_ids),
            "batch_sizes": [
                len(
                    inference.processed_candidate_ids[
                        index : index + MAX_CANDIDATE_PAIRS_PER_BATCH
                    ]
                )
                for index in range(
                    0,
                    len(inference.processed_candidate_ids),
                    MAX_CANDIDATE_PAIRS_PER_BATCH,
                )
            ],
            "request_phase": "deferred" if candidate_ids is not None else "inline",
            "resolved_edges": len(resolved_edges),
        }
        if dry_run:
            diagnostics["preview_edges"] = [
                {
                    "candidate_id": edge.candidate_id,
                    "from_entity_id": edge.from_entity_id,
                    "to_entity_id": edge.to_entity_id,
                    "nature": edge.nature,
                    "confidence": edge.confidence,
                    "quote": edge.quote,
                }
                for edge in resolved_edges
            ]

        summary = build_auto_connections_summary(
            enabled=True,
            eligible=True,
            reason=eligibility.reason,
            families=family_results,
            write_result=write_result,
            created_cap_skipped=created_cap_skipped,
            diagnostics=diagnostics,
            deferred_candidate_ids=(
                inference.overflow_candidate_ids if defer_overflow else ()
            ),
        )
        if not defer_overflow and inference.overflow_candidate_ids:
            summary["unprocessed_candidate_ids"] = list(
                inference.overflow_candidate_ids
            )
            summary["unprocessed"] = len(inference.overflow_candidate_ids)
        else:
            summary["unprocessed"] = 0
        summary["dry_run"] = dry_run
        return summary
    except Exception as exc:
        logger.warning(
            "Auto-connection inference failed for project_id=%s article_id=%s: %s",
            project_id,
            article_id,
            exc,
            exc_info=True,
        )
        return build_auto_connections_summary(
            enabled=True,
            eligible=True,
            reason=eligibility.reason,
            error=str(exc),
        )
