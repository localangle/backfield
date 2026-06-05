"""Embed pending semantic documents during Backfield Output (worker-local)."""

from __future__ import annotations

import logging

from backfield_ai.embeddings import EmbeddingConfigurationError, embed_texts_for_model_config
from backfield_ai.model_resolve import resolve_semantic_embedding_model_config_id
from backfield_entities.ingest.semantic_indexing.db_output import (
    semantic_entity_types_for_consolidated_domains,
)
from backfield_entities.ingest.semantic_indexing.embedding import (
    apply_embedding_batch_outcomes,
    collect_pending_semantic_documents,
    plan_embedding_batches,
)
from backfield_entities.ingest.semantic_indexing.embedding_contract import (
    EmbeddingRunSummary,
    EmbeddingVectorOutcome,
)
from sqlmodel import Session

logger = logging.getLogger(__name__)


def embed_pending_semantic_documents(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    entity_types: tuple[str, ...],
) -> EmbeddingRunSummary:
    """Batch-embed pending semantic documents for one article scope."""
    pending = collect_pending_semantic_documents(
        session,
        project_id=project_id,
        article_id=article_id,
        entity_types=entity_types,
    )
    if not pending:
        return EmbeddingRunSummary(status="skipped", pending=0)

    try:
        model_config_id = resolve_semantic_embedding_model_config_id(session, project_id)
    except EmbeddingConfigurationError as exc:
        logger.warning(
            "Semantic embedding skipped for project_id=%s article_id=%s: %s",
            project_id,
            article_id,
            exc,
        )
        return EmbeddingRunSummary(
            status="not_configured",
            pending=len(pending),
            error=str(exc),
        )

    batches = plan_embedding_batches(pending)
    summary = EmbeddingRunSummary(
        status="succeeded",
        model_config_id=model_config_id,
        pending=len(pending),
        batches=len(batches),
    )

    for batch in batches:
        try:
            result = embed_texts_for_model_config(
                session,
                project_id=project_id,
                model_config_id=model_config_id,
                texts=batch.texts(),
            )
        except EmbeddingConfigurationError as exc:
            logger.warning(
                "Semantic embedding batch failed for project_id=%s article_id=%s: %s",
                project_id,
                article_id,
                exc,
                exc_info=True,
            )
            outcomes = [
                EmbeddingVectorOutcome(document=doc, vector=None, error_message=str(exc))
                for doc in batch.documents
            ]
            apply_summary = apply_embedding_batch_outcomes(
                session,
                outcomes=outcomes,
                embedding_model=model_config_id,
                embedding_dimensions=None,
            )
            summary.indexed += apply_summary.indexed
            summary.failed += apply_summary.failed
            summary.skipped += apply_summary.skipped
            summary.status = "partial" if summary.indexed else "failed"
            summary.error = str(exc)
            continue

        if summary.embedding_model is None:
            summary.embedding_model = result.litellm_model
        if summary.embedding_dimensions is None and result.dimensions is not None:
            summary.embedding_dimensions = result.dimensions

        batch_error = result.batch_error
        outcomes = [
            EmbeddingVectorOutcome(
                document=batch.documents[i],
                vector=item.vector,
                error_message=item.error_message or batch_error,
            )
            for i, item in enumerate(result.items)
        ]
        apply_summary = apply_embedding_batch_outcomes(
            session,
            outcomes=outcomes,
            embedding_model=result.litellm_model,
            embedding_dimensions=result.dimensions,
        )
        summary.indexed += apply_summary.indexed
        summary.failed += apply_summary.failed
        summary.skipped += apply_summary.skipped

        if batch_error or apply_summary.failed:
            summary.status = "partial" if summary.indexed else "failed"
            summary.error = batch_error or "One or more semantic documents failed to embed."

    if summary.failed and summary.indexed:
        summary.status = "partial"
    elif summary.failed and not summary.indexed:
        summary.status = "failed"
    elif summary.indexed:
        summary.status = "succeeded"

    return summary


def embed_pending_semantic_documents_for_db_output(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    consolidated_domain_keys: tuple[str, ...],
) -> EmbeddingRunSummary:
    """Batch-embed pending semantic documents after Backfield Output."""
    entity_types = semantic_entity_types_for_consolidated_domains(consolidated_domain_keys)
    return embed_pending_semantic_documents(
        session,
        project_id=project_id,
        article_id=article_id,
        entity_types=entity_types,
    )
