"""Persist article-level metadata tags from consolidated DBOutput payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from backfield_db import SubstrateArticleMeta
from sqlmodel import Session, select

from backfield_entities.ingest.db_output_settings import ReconciliationPolicy

ArticleMetadataPersistStatus = Literal["not_present", "skipped", "succeeded", "failed"]


def _article_metadata_block(consolidated: dict[str, Any]) -> dict[str, Any] | None:
    raw = consolidated.get("article_metadata")
    return raw if isinstance(raw, dict) else None


def _normalize_confidence(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value < 0.0 or value > 1.0:
        return None
    return value


def persist_article_metadata_after_db_output(
    session: Session,
    *,
    article_id: int,
    consolidated: dict[str, Any],
    policy: ReconciliationPolicy,
    source_run_id: str | None = None,
) -> dict[str, Any]:
    """Upsert ``substrate_article_meta`` when ``article_metadata`` is present."""
    block = _article_metadata_block(consolidated)
    if block is None:
        return {"status": "not_present", "persisted": False}

    meta_type = str(block.get("meta_type") or "").strip()
    if not meta_type:
        return {
            "status": "failed",
            "persisted": False,
            "error": "article_metadata.meta_type is required",
        }

    category = str(block.get("category") or "").strip()
    if not category:
        return {
            "status": "failed",
            "persisted": False,
            "error": "article_metadata.category is required",
        }

    rationale = str(block.get("rationale") or "").strip()
    if not rationale:
        return {
            "status": "failed",
            "persisted": False,
            "error": "article_metadata.rationale is required",
        }

    confidence = _normalize_confidence(block.get("confidence"))
    if confidence is None:
        return {
            "status": "failed",
            "persisted": False,
            "error": "article_metadata.confidence must be a number from 0.0 to 1.0",
        }

    prompt_preset_raw = block.get("prompt_preset")
    prompt_preset = (
        prompt_preset_raw.strip()
        if isinstance(prompt_preset_raw, str) and prompt_preset_raw.strip()
        else None
    )

    existing = session.exec(
        select(SubstrateArticleMeta).where(
            SubstrateArticleMeta.article_id == article_id,
            SubstrateArticleMeta.meta_type == meta_type,
        )
    ).first()

    if policy == "add_only" and existing is not None:
        return {
            "status": "skipped",
            "persisted": False,
            "meta_type": meta_type,
            "category": existing.category,
            "reason": "add_only",
        }

    if policy == "smart_merge" and existing is not None:
        existing_preset = existing.prompt_preset or ""
        incoming_preset = prompt_preset or ""
        if (
            existing.category == category
            and existing.rationale == rationale
            and float(existing.confidence) == confidence
            and existing_preset == incoming_preset
        ):
            return {
                "status": "skipped",
                "persisted": False,
                "meta_type": meta_type,
                "category": existing.category,
                "reason": "unchanged",
            }

    now = datetime.now(UTC)
    if existing is None:
        row = SubstrateArticleMeta(
            article_id=article_id,
            meta_type=meta_type,
            category=category,
            rationale=rationale,
            confidence=confidence,
            prompt_preset=prompt_preset,
            source_run_id=source_run_id,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.flush()
        action = "created"
    else:
        existing.category = category
        existing.rationale = rationale
        existing.confidence = confidence
        existing.prompt_preset = prompt_preset
        existing.source_run_id = source_run_id
        existing.updated_at = now
        session.add(existing)
        session.flush()
        action = "updated" if policy != "replace" else "replaced"

    return {
        "status": "succeeded",
        "persisted": True,
        "action": action,
        "meta_type": meta_type,
        "category": category,
        "confidence": confidence,
    }
