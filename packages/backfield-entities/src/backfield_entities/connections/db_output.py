"""Backfield Output integration for automatic connection inference."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlmodel import Session

from backfield_entities.connections.affiliation_links import (
    infer_affiliation_person_organization_edges,
)
from backfield_entities.connections.caps import MAX_CREATED_EDGES_PER_ITEM
from backfield_entities.connections.context import (
    AutoConnectionArticleContext,
    collect_auto_connection_article_context,
)
from backfield_entities.connections.dedupe import (
    connection_edge_key,
)
from backfield_entities.connections.eligibility import evaluate_auto_connections_eligibility
from backfield_entities.connections.inference import (
    AUTO_CONNECTION_FAMILIES,
    FamilyInferenceResult,
    classify_connection_family,
)
from backfield_entities.connections.same_site_hints import discover_same_site_org_location_hints
from backfield_entities.connections.summary import build_auto_connections_summary
from backfield_entities.connections.types import (
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
        family_results: list[FamilyInferenceResult] = []
        pending_edges: list[
            tuple[
                str,
                str,
                tuple[LinkedEntitySnapshot, ...],
                tuple[LinkedEntitySnapshot, ...],
                AutoConnectionEdgeProposal,
            ]
        ] = []
        pending_edge_keys: set[tuple[int, str, str, str, str, str, str]] = set()

        for from_type, to_type in AUTO_CONNECTION_FAMILIES:
            from_entities, to_entities = _family_entities(
                context,
                from_entity_type=from_type,
                to_entity_type=to_type,
            )
            if not from_entities or not to_entities:
                continue
            if from_type == "person" and to_type == "organization":
                for edge in infer_affiliation_person_organization_edges(
                    people=from_entities,
                    organizations=to_entities,
                    article_text=context.article_text,
                ):
                    edge_key = connection_edge_key(
                        project_id=project_id,
                        from_entity_type=from_type,
                        from_entity_id=edge.from_entity_id,
                        to_entity_type=to_type,
                        to_entity_id=edge.to_entity_id,
                        nature=edge.nature,
                        description=edge.description,
                    )
                    if edge_key in pending_edge_keys:
                        continue
                    pending_edge_keys.add(edge_key)
                    pending_edges.append(
                        (from_type, to_type, from_entities, to_entities, edge)
                    )
            same_site_hints = ()
            if from_type == "organization" and to_type == "location":
                same_site_hints = discover_same_site_org_location_hints(
                    organizations=from_entities,
                    locations=to_entities,
                    article_text=context.article_text,
                )
            result = classify_connection_family(
                from_entity_type=from_type,
                to_entity_type=to_type,
                from_entities=from_entities,
                to_entities=to_entities,
                article_text=context.article_text,
                model=model,
                model_config_id=model_config_id,
                call_llm=call_llm,
                same_site_hints=same_site_hints,
            )
            family_results.append(result)
            for edge in result.edges:
                edge_key = connection_edge_key(
                    project_id=project_id,
                    from_entity_type=from_type,
                    from_entity_id=edge.from_entity_id,
                    to_entity_type=to_type,
                    to_entity_id=edge.to_entity_id,
                    nature=edge.nature,
                    description=edge.description,
                )
                if edge_key in pending_edge_keys:
                    continue
                pending_edge_keys.add(edge_key)
                pending_edges.append((from_type, to_type, from_entities, to_entities, edge))

        created_cap_skipped = 0
        if len(pending_edges) > MAX_CREATED_EDGES_PER_ITEM:
            created_cap_skipped = len(pending_edges) - MAX_CREATED_EDGES_PER_ITEM
            pending_edges = pending_edges[:MAX_CREATED_EDGES_PER_ITEM]

        write_result = AutoConnectionWriteResult(created=[], skipped_existing_count=0)
        for from_type, to_type, from_entities, to_entities, edge in pending_edges:
            batch = write_auto_connections(
                session,
                project_id=project_id,
                from_entity_type=from_type,
                to_entity_type=to_type,
                from_entities=from_entities,
                to_entities=to_entities,
                edges=[edge],
                article_id=article_id,
                run_id=run_id,
                processed_item_id=processed_item_id,
                adjudication_model=model,
                adjudication_ai_model_config_id=model_config_id,
            )
            write_result.created.extend(batch.created)
            write_result.skipped_existing_count += batch.skipped_existing_count

        return build_auto_connections_summary(
            enabled=True,
            eligible=True,
            reason=eligibility.reason,
            families=family_results,
            write_result=write_result,
            created_cap_skipped=created_cap_skipped,
        )
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
