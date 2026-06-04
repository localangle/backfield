"""Backfield Output integration for semantic document synchronization."""

from __future__ import annotations

import logging
from typing import Any

from sqlmodel import Session

from backfield_stylebook.semantic_indexing.contracts import SemanticBuilderEntityType
from backfield_stylebook.semantic_indexing.embedding_contract import EmbeddingRunSummary
from backfield_stylebook.semantic_indexing.sync import sync_semantic_documents_for_article
from backfield_stylebook.semantic_indexing.sync_contract import SemanticSyncResult

logger = logging.getLogger(__name__)

CONSOLIDATED_DOMAIN_TO_SEMANTIC_ENTITY_TYPE: dict[str, SemanticBuilderEntityType] = {
    "people": "person",
    "places": "location",
}


def semantic_entity_types_for_consolidated_domains(
    domain_keys: tuple[str, ...],
) -> tuple[SemanticBuilderEntityType, ...]:
    """Map persisted consolidated domains to semantic builder entity types."""
    mapped: list[SemanticBuilderEntityType] = []
    for key in domain_keys:
        entity_type = CONSOLIDATED_DOMAIN_TO_SEMANTIC_ENTITY_TYPE.get(key)
        if entity_type is not None and entity_type not in mapped:
            mapped.append(entity_type)
    return tuple(mapped)


def sync_semantic_documents_after_db_output(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    consolidated_domain_keys: tuple[str, ...],
) -> SemanticSyncResult:
    """Synchronize semantic documents for domains persisted by Backfield Output."""
    entity_types = semantic_entity_types_for_consolidated_domains(consolidated_domain_keys)
    if not entity_types:
        return SemanticSyncResult(summaries=())
    return sync_semantic_documents_for_article(
        session,
        project_id=project_id,
        article_id=article_id,
        entity_types=entity_types,
    )


def build_semantic_indexing_summary(
    *,
    enabled: bool,
    sync_result: SemanticSyncResult | None = None,
    error: str | None = None,
    embedding: EmbeddingRunSummary | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact semantic indexing summary for Backfield Output results."""
    if not enabled:
        return {"enabled": False, "status": "not_enabled", "domains": []}
    if error:
        return {
            "enabled": True,
            "status": "failed",
            "error": error,
            "domains": [],
        }
    domains = [summary.as_dict() for summary in (sync_result.summaries if sync_result else ())]
    out: dict[str, Any] = {
        "enabled": True,
        "status": "succeeded",
        "domains": domains,
    }
    if embedding is not None:
        if isinstance(embedding, EmbeddingRunSummary):
            out["embedding"] = embedding.as_dict()
        else:
            out["embedding"] = embedding
        out["status"] = _combined_semantic_indexing_status(out["status"], out["embedding"])
    return out


def _combined_semantic_indexing_status(
    sync_status: str,
    embedding_summary: dict[str, Any],
) -> str:
    if sync_status == "failed":
        return "failed"
    emb_status = str(embedding_summary.get("status") or "")
    if emb_status in ("failed", "partial", "not_configured"):
        return "partial"
    return sync_status


def run_semantic_indexing_for_db_output(
    session: Session,
    *,
    project_id: int,
    article_id: int,
    consolidated_domain_keys: tuple[str, ...],
    embedding: EmbeddingRunSummary | dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run semantic sync after substrate persistence; warn instead of raising."""
    try:
        sync_result = sync_semantic_documents_after_db_output(
            session,
            project_id=project_id,
            article_id=article_id,
            consolidated_domain_keys=consolidated_domain_keys,
        )
    except Exception as exc:
        logger.warning(
            "Semantic indexing failed for project_id=%s article_id=%s: %s",
            project_id,
            article_id,
            exc,
            exc_info=True,
        )
        return build_semantic_indexing_summary(enabled=True, error=str(exc))
    return build_semantic_indexing_summary(
        enabled=True,
        sync_result=sync_result,
        embedding=embedding,
    )
