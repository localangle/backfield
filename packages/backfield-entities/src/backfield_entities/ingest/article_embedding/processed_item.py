"""Compact article embedding status for processed item detail."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from backfield_db import SubstrateArticleEmbedding
from sqlmodel import Session, select

ProcessedItemArticleEmbeddingStatus = Literal[
    "not_present",
    "pending",
    "running",
    "succeeded",
    "skipped",
    "failed",
]


def _empty_summary(
    *,
    status: ProcessedItemArticleEmbeddingStatus = "not_present",
) -> dict[str, Any]:
    return {
        "status": status,
        "present": False,
        "persisted": False,
        "embedding_model": None,
        "embedding_dimensions": None,
        "embedded_at": None,
        "error": None,
    }


def _find_article_embedding_in_output(result_obj: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(result_obj, dict):
        return None
    direct = result_obj.get("article_embedding")
    if isinstance(direct, dict):
        return direct
    for key, value in result_obj.items():
        if key == "stylebook_output" and isinstance(value, dict):
            nested = value.get("article_embedding")
            if isinstance(nested, dict):
                return nested
        if isinstance(value, dict):
            nested = value.get("article_embedding")
            if isinstance(nested, dict) and isinstance(nested.get("embedding"), list):
                return nested
    return None


def _persist_summary_from_stylebook_output(
    result_obj: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(result_obj, dict):
        return None
    block = result_obj.get("stylebook_output")
    if not isinstance(block, dict):
        return None
    raw = block.get("article_embedding_persist")
    return raw if isinstance(raw, dict) else None


def build_processed_item_article_embedding_summary(
    session: Session | None,
    *,
    item_status: str,
    result_obj: dict[str, Any] | None,
    article_id: int | None = None,
    item_updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Derive compact article embedding status for processed item Info tab."""
    if item_status == "pending":
        return _empty_summary(status="pending")
    if item_status == "running":
        return _empty_summary(status="running")

    persist_raw = _persist_summary_from_stylebook_output(result_obj)
    output_block = _find_article_embedding_in_output(result_obj)

    if session is not None and article_id is not None:
        row = session.exec(
            select(SubstrateArticleEmbedding).where(
                SubstrateArticleEmbedding.article_id == article_id
            )
        ).first()
        if row is not None:
            return {
                "status": "succeeded",
                "present": True,
                "persisted": True,
                "embedding_model": row.embedding_model,
                "embedding_dimensions": row.embedding_dimensions,
                "embedded_at": row.updated_at,
                "error": None,
            }

    if persist_raw is not None:
        status_raw = persist_raw.get("status")
        status: ProcessedItemArticleEmbeddingStatus
        if status_raw == "skipped":
            status = "skipped"
        elif status_raw == "failed":
            status = "failed"
        elif status_raw == "succeeded":
            status = "succeeded"
        else:
            status = "not_present"
        return {
            "status": status,
            "present": status in ("succeeded", "skipped"),
            "persisted": bool(persist_raw.get("persisted")),
            "embedding_model": persist_raw.get("embedding_model"),
            "embedding_dimensions": persist_raw.get("embedding_dimensions"),
            "embedded_at": item_updated_at,
            "error": persist_raw.get("error"),
        }

    if output_block is not None and isinstance(output_block.get("embedding"), list):
        model = output_block.get("embedding_model")
        dims = output_block.get("embedding_dimensions")
        return {
            "status": "succeeded",
            "present": True,
            "persisted": False,
            "embedding_model": model if isinstance(model, str) else None,
            "embedding_dimensions": int(dims) if dims is not None else None,
            "embedded_at": item_updated_at,
            "error": None,
        }

    return _empty_summary()
