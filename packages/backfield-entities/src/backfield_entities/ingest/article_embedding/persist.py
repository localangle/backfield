"""Persist article-level embeddings from consolidated DBOutput payloads."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from backfield_db import SubstrateArticleEmbedding
from sqlmodel import Session, select

from backfield_entities.ingest.db_output_settings import ReconciliationPolicy

ArticleEmbeddingPersistStatus = Literal["not_present", "skipped", "succeeded", "failed"]


def _article_embedding_block(consolidated: dict[str, Any]) -> dict[str, Any] | None:
    raw = consolidated.get("article_embedding")
    return raw if isinstance(raw, dict) else None


def persist_article_embedding_after_db_output(
    session: Session,
    *,
    article_id: int,
    consolidated: dict[str, Any],
    policy: ReconciliationPolicy,
) -> dict[str, Any]:
    """Upsert ``substrate_article_embedding`` when ``article_embedding`` is present."""
    block = _article_embedding_block(consolidated)
    if block is None:
        existing = session.exec(
            select(SubstrateArticleEmbedding).where(
                SubstrateArticleEmbedding.article_id == article_id
            )
        ).first()
        if policy == "replace" and existing is not None:
            session.delete(existing)
            session.flush()
            return {"status": "succeeded", "action": "deleted", "persisted": False}
        return {"status": "not_present", "persisted": False}

    vector = block.get("embedding")
    if not isinstance(vector, list) or not vector:
        return {
            "status": "failed",
            "persisted": False,
            "error": "article_embedding.embedding must be a non-empty vector",
        }

    embedded_text = str(block.get("embedded_text") or "").strip()
    if not embedded_text:
        return {
            "status": "failed",
            "persisted": False,
            "error": "article_embedding.embedded_text is required",
        }

    model = str(block.get("embedding_model") or "").strip()
    if not model:
        return {
            "status": "failed",
            "persisted": False,
            "error": "article_embedding.embedding_model is required",
        }

    dimensions_raw = block.get("embedding_dimensions")
    dimensions = int(dimensions_raw) if dimensions_raw is not None else len(vector)
    config_id_raw = block.get("embedding_ai_model_config_id")
    config_id = (
        config_id_raw.strip()
        if isinstance(config_id_raw, str) and config_id_raw.strip()
        else None
    )

    existing = session.exec(
        select(SubstrateArticleEmbedding).where(SubstrateArticleEmbedding.article_id == article_id)
    ).first()

    if policy == "add_only" and existing is not None:
        return {
            "status": "skipped",
            "persisted": False,
            "embedding_model": existing.embedding_model,
            "embedding_dimensions": existing.embedding_dimensions,
            "reason": "add_only",
        }

    if (
        policy == "smart_merge"
        and existing is not None
        and existing.embedded_text == embedded_text
        and existing.embedding_model == model
    ):
        return {
            "status": "skipped",
            "persisted": False,
            "embedding_model": existing.embedding_model,
            "embedding_dimensions": existing.embedding_dimensions,
            "reason": "unchanged",
        }

    now = datetime.now(UTC)
    bind = session.get_bind()
    embedding_value: object = list(vector)
    if bind.dialect.name != "postgresql":
        embedding_value = json.dumps(list(vector))

    if existing is None:
        row = SubstrateArticleEmbedding(
            article_id=article_id,
            embedded_text=embedded_text,
            embedding_model=model,
            embedding_dimensions=dimensions,
            embedding_ai_model_config_id=config_id,
            embedding=embedding_value,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        action = "created"
    else:
        existing.embedded_text = embedded_text
        existing.embedding_model = model
        existing.embedding_dimensions = dimensions
        existing.embedding_ai_model_config_id = config_id
        existing.embedding = embedding_value
        existing.updated_at = now
        session.add(existing)
        session.flush()
        action = "updated"

    return {
        "status": "succeeded",
        "persisted": True,
        "action": action,
        "embedding_model": model,
        "embedding_dimensions": dimensions,
    }
