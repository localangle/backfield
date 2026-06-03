"""Compact semantic indexing summary for processed item detail (Issue 7)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from backfield_db import SubstrateLocationSemanticDocument, SubstratePersonSemanticDocument
from backfield_db.semantic_indexing import (
    SEMANTIC_EMBEDDING_STATUS_FAILED,
    SEMANTIC_EMBEDDING_STATUS_PENDING,
    SEMANTIC_EMBEDDING_STATUS_READY,
)
from sqlmodel import Session, select

ProcessedItemSemanticStatus = Literal[
    "not_enabled",
    "pending",
    "running",
    "succeeded",
    "partial",
    "failed",
]


def extract_db_output_semantic_indexing(
    result_obj: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Read ``semantic_indexing`` from Backfield Output on ``stylebook_output``."""
    if not isinstance(result_obj, dict):
        return None
    block = result_obj.get("stylebook_output")
    if not isinstance(block, dict):
        return None
    raw = block.get("semantic_indexing")
    return raw if isinstance(raw, dict) else None


def _empty_summary(*, status: ProcessedItemSemanticStatus, enabled: bool = False) -> dict[str, Any]:
    return {
        "status": status,
        "enabled": enabled,
        "document_count": 0,
        "indexed_count": 0,
        "pending_count": 0,
        "failed_count": 0,
        "indexed_at": None,
        "embedding_model": None,
        "error": None,
    }


def _counts_from_output(raw: dict[str, Any]) -> dict[str, int]:
    embedding = raw.get("embedding")
    emb = embedding if isinstance(embedding, dict) else {}
    indexed_count = int(emb.get("indexed") or 0)
    failed_count = int(emb.get("failed") or 0)
    pending_count = int(emb.get("pending") or 0)
    document_count = indexed_count + failed_count + pending_count

    domains = raw.get("domains")
    if isinstance(domains, list):
        for domain in domains:
            if not isinstance(domain, dict):
                continue
            created = int(domain.get("created") or 0)
            updated = int(domain.get("updated") or 0)
            unchanged = int(domain.get("unchanged") or 0)
            document_count = max(document_count, created + updated + unchanged)
            pending_count += int(domain.get("pending") or 0)

    return {
        "document_count": document_count,
        "indexed_count": indexed_count,
        "pending_count": pending_count,
        "failed_count": failed_count,
    }


def _article_semantic_document_stats(
    session: Session,
    *,
    project_id: int,
    article_id: int,
) -> dict[str, Any]:
    total = 0
    indexed = 0
    pending = 0
    failed = 0
    latest_embedded_at: datetime | None = None
    embedding_model: str | None = None

    for model in (SubstratePersonSemanticDocument, SubstrateLocationSemanticDocument):
        rows = session.exec(
            select(model).where(
                model.project_id == project_id,
                model.article_id == article_id,
                model.active.is_(True),
            )
        ).all()
        for row in rows:
            total += 1
            if row.embedding_status == SEMANTIC_EMBEDDING_STATUS_READY:
                indexed += 1
                embedded_at = row.embedded_at
                if embedded_at is not None and (
                    latest_embedded_at is None or embedded_at > latest_embedded_at
                ):
                    latest_embedded_at = embedded_at
                if row.embedding_model and not embedding_model:
                    embedding_model = str(row.embedding_model)
            elif row.embedding_status == SEMANTIC_EMBEDDING_STATUS_PENDING:
                pending += 1
            elif row.embedding_status == SEMANTIC_EMBEDDING_STATUS_FAILED:
                failed += 1

    return {
        "document_count": total,
        "indexed_count": indexed,
        "pending_count": pending,
        "failed_count": failed,
        "latest_embedded_at": latest_embedded_at,
        "embedding_model": embedding_model,
    }


def _resolve_semantic_indexing_status(
    *,
    output_status: str,
    indexed_count: int,
    pending_count: int,
    failed_count: int,
) -> ProcessedItemSemanticStatus:
    if output_status == "failed":
        return "failed"
    if pending_count > 0:
        return "partial"
    if failed_count > 0:
        return "partial" if indexed_count > 0 else "failed"
    if output_status == "partial":
        return "partial"
    if output_status in ("succeeded", "failed", "partial"):
        return output_status  # type: ignore[return-value]
    if indexed_count > 0:
        return "succeeded"
    return "succeeded"


def build_processed_item_semantic_indexing_summary(
    session: Session | None,
    *,
    project_id: int,
    item_status: str,
    result_obj: dict[str, Any] | None,
    article_id: int | None = None,
    item_updated_at: datetime | None = None,
) -> dict[str, Any]:
    """Derive compact semantic indexing status for processed item detail."""
    if item_status == "pending":
        return _empty_summary(status="pending")
    if item_status == "running":
        return _empty_summary(status="running")

    raw = extract_db_output_semantic_indexing(result_obj)
    stored_enabled = bool(raw and raw.get("enabled"))

    if session is not None and article_id is not None and project_id > 0:
        db_stats = _article_semantic_document_stats(
            session,
            project_id=project_id,
            article_id=article_id,
        )
        if db_stats["document_count"] > 0 and not stored_enabled:
            status = _resolve_semantic_indexing_status(
                output_status="succeeded",
                indexed_count=int(db_stats["indexed_count"]),
                pending_count=int(db_stats["pending_count"]),
                failed_count=int(db_stats["failed_count"]),
            )
            return {
                "status": status,
                "enabled": True,
                "document_count": db_stats["document_count"],
                "indexed_count": db_stats["indexed_count"],
                "pending_count": db_stats["pending_count"],
                "failed_count": db_stats["failed_count"],
                "indexed_at": db_stats["latest_embedded_at"],
                "embedding_model": db_stats["embedding_model"],
                "error": None,
            }

    if raw is None or not raw.get("enabled"):
        return _empty_summary(status="not_enabled")

    output_status = str(raw.get("status") or "succeeded")
    counts = _counts_from_output(raw)
    embedding = raw.get("embedding")
    emb = embedding if isinstance(embedding, dict) else {}
    embedding_model = emb.get("embedding_model")
    model_label = embedding_model if isinstance(embedding_model, str) else None
    error_raw = raw.get("error") or emb.get("error")
    error = error_raw if isinstance(error_raw, str) and error_raw.strip() else None

    indexed_at: datetime | None = None
    if session is not None and article_id is not None and project_id > 0:
        db_stats = _article_semantic_document_stats(
            session,
            project_id=project_id,
            article_id=article_id,
        )
        counts = {
            "document_count": db_stats["document_count"],
            "indexed_count": db_stats["indexed_count"],
            "pending_count": db_stats["pending_count"],
            "failed_count": db_stats["failed_count"],
        }
        indexed_at = db_stats["latest_embedded_at"]
        if db_stats["embedding_model"]:
            model_label = db_stats["embedding_model"]

    status = _resolve_semantic_indexing_status(
        output_status=output_status,
        indexed_count=counts["indexed_count"],
        pending_count=counts["pending_count"],
        failed_count=counts["failed_count"],
    )
    if indexed_at is None and item_updated_at is not None and status in ("succeeded", "partial"):
        indexed_at = item_updated_at

    return {
        "status": status,
        "enabled": True,
        "document_count": counts["document_count"],
        "indexed_count": counts["indexed_count"],
        "pending_count": counts["pending_count"],
        "failed_count": counts["failed_count"],
        "indexed_at": indexed_at,
        "embedding_model": model_label,
        "error": error,
    }
