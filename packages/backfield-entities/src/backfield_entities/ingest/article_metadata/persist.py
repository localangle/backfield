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


def _normalize_metadata_item(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    category = str(raw.get("category") or "").strip()
    rationale = str(raw.get("rationale") or "").strip()
    confidence = _normalize_confidence(raw.get("confidence"))
    if not category or not rationale or confidence is None:
        return None
    return {
        "category": category,
        "rationale": rationale,
        "confidence": confidence,
    }


def _multi_value_items_from_block(block: dict[str, Any]) -> list[dict[str, Any]]:
    for list_key in ("subjects", "needs"):
        raw_items = block.get(list_key)
        if isinstance(raw_items, list):
            items: list[dict[str, Any]] = []
            for entry in raw_items:
                normalized = _normalize_metadata_item(entry)
                if normalized is not None:
                    items.append(normalized)
            if items:
                return items

    normalized = _normalize_metadata_item(
        {
            "category": block.get("category"),
            "rationale": block.get("rationale"),
            "confidence": block.get("confidence"),
        }
    )
    return [normalized] if normalized is not None else []


def _block_has_multi_value_list(block: dict[str, Any]) -> bool:
    return isinstance(block.get("subjects"), list) or isinstance(block.get("needs"), list)


def _upsert_metadata_row(
    session: Session,
    *,
    article_id: int,
    meta_type: str,
    item: dict[str, Any],
    prompt_preset: str | None,
    source_run_id: str | None,
    now: datetime,
) -> tuple[str, bool]:
    existing = session.exec(
        select(SubstrateArticleMeta).where(
            SubstrateArticleMeta.article_id == article_id,
            SubstrateArticleMeta.meta_type == meta_type,
            SubstrateArticleMeta.category == item["category"],
        )
    ).first()

    if existing is None:
        session.add(
            SubstrateArticleMeta(
                article_id=article_id,
                meta_type=meta_type,
                category=item["category"],
                rationale=item["rationale"],
                confidence=item["confidence"],
                prompt_preset=prompt_preset,
                source_run_id=source_run_id,
                created_at=now,
                updated_at=now,
            )
        )
        return "created", True

    existing_preset = existing.prompt_preset or ""
    incoming_preset = prompt_preset or ""
    if (
        existing.rationale == item["rationale"]
        and float(existing.confidence) == item["confidence"]
        and existing_preset == incoming_preset
    ):
        return "unchanged", False

    existing.rationale = item["rationale"]
    existing.confidence = item["confidence"]
    existing.prompt_preset = prompt_preset
    existing.source_run_id = source_run_id
    existing.updated_at = now
    session.add(existing)
    return "updated", True


def _persist_multi_value_block(
    session: Session,
    *,
    article_id: int,
    block: dict[str, Any],
    policy: ReconciliationPolicy,
    source_run_id: str | None,
) -> dict[str, Any]:
    meta_type = str(block.get("meta_type") or "").strip()
    if not meta_type:
        return {
            "status": "failed",
            "persisted": False,
            "error": "article_metadata.meta_type is required",
        }

    items = _multi_value_items_from_block(block)
    if not items:
        return {
            "status": "failed",
            "persisted": False,
            "error": "article_metadata must include at least one valid multi-value item",
        }

    prompt_preset_raw = block.get("prompt_preset")
    prompt_preset = (
        prompt_preset_raw.strip()
        if isinstance(prompt_preset_raw, str) and prompt_preset_raw.strip()
        else None
    )

    existing_rows = session.exec(
        select(SubstrateArticleMeta).where(
            SubstrateArticleMeta.article_id == article_id,
            SubstrateArticleMeta.meta_type == meta_type,
        )
    ).all()
    incoming_categories = {item["category"] for item in items}

    if policy == "add_only" and existing_rows:
        existing_categories = {row.category for row in existing_rows}
        items = [item for item in items if item["category"] not in existing_categories]
        if not items:
            return {
                "status": "skipped",
                "persisted": False,
                "meta_type": meta_type,
                "reason": "add_only",
            }

    now = datetime.now(UTC)
    if policy in {"replace", "smart_merge"}:
        for row in existing_rows:
            if row.category not in incoming_categories:
                session.delete(row)

    actions: list[str] = []
    persisted_any = False
    for item in items:
        action, persisted = _upsert_metadata_row(
            session,
            article_id=article_id,
            meta_type=meta_type,
            item=item,
            prompt_preset=prompt_preset,
            source_run_id=source_run_id,
            now=now,
        )
        if persisted:
            persisted_any = True
            if action not in actions:
                actions.append(action)
        elif action == "unchanged" and not actions:
            actions.append("unchanged")

    if not persisted_any and actions == ["unchanged"]:
        return {
            "status": "skipped",
            "persisted": False,
            "meta_type": meta_type,
            "categories": sorted(incoming_categories),
            "reason": "unchanged",
        }

    session.flush()
    return {
        "status": "succeeded",
        "persisted": True,
        "action": actions[0] if len(actions) == 1 else "mixed",
        "meta_type": meta_type,
        "categories": sorted(incoming_categories),
        "item_count": len(items),
    }


def _article_metadata_blocks(consolidated: dict[str, Any]) -> list[dict[str, Any]]:
    all_raw = consolidated.get("article_metadata_all")
    if isinstance(all_raw, list):
        blocks = [
            block
            for block in all_raw
            if isinstance(block, dict) and str(block.get("meta_type") or "").strip()
        ]
        if blocks:
            return blocks
    single = _article_metadata_block(consolidated)
    return [single] if single is not None else []


def _persist_one_article_metadata_block(
    session: Session,
    *,
    article_id: int,
    block: dict[str, Any],
    policy: ReconciliationPolicy,
    source_run_id: str | None = None,
) -> dict[str, Any]:
    if _block_has_multi_value_list(block):
        return _persist_multi_value_block(
            session,
            article_id=article_id,
            block=block,
            policy=policy,
            source_run_id=source_run_id,
        )

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

    existing_rows = session.exec(
        select(SubstrateArticleMeta).where(
            SubstrateArticleMeta.article_id == article_id,
            SubstrateArticleMeta.meta_type == meta_type,
        )
    ).all()
    existing = next((row for row in existing_rows if row.category == category), None)

    if policy == "add_only" and existing_rows:
        return {
            "status": "skipped",
            "persisted": False,
            "meta_type": meta_type,
            "category": existing_rows[0].category,
            "reason": "add_only",
        }

    if policy in {"replace", "smart_merge"}:
        for row in existing_rows:
            if row.category != category:
                session.delete(row)

    if policy == "smart_merge" and existing is not None:
        existing_preset = existing.prompt_preset or ""
        incoming_preset = prompt_preset or ""
        if (
            existing.rationale == rationale
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
    had_existing_rows = bool(existing_rows)
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
        if policy == "replace" and had_existing_rows:
            action = "replaced"
        else:
            action = "created"
    else:
        existing.rationale = rationale
        existing.confidence = confidence
        existing.prompt_preset = prompt_preset
        existing.source_run_id = source_run_id
        existing.updated_at = now
        session.add(existing)
        session.flush()
        action = "replaced" if policy == "replace" else "updated"

    return {
        "status": "succeeded",
        "persisted": True,
        "action": action,
        "meta_type": meta_type,
        "category": category,
        "confidence": confidence,
    }


def persist_article_metadata_after_db_output(
    session: Session,
    *,
    article_id: int,
    consolidated: dict[str, Any],
    policy: ReconciliationPolicy,
    source_run_id: str | None = None,
) -> dict[str, Any]:
    """Upsert ``substrate_article_meta`` when ``article_metadata`` is present."""
    blocks = _article_metadata_blocks(consolidated)
    if not blocks:
        return {"status": "not_present", "persisted": False}

    if len(blocks) == 1:
        return _persist_one_article_metadata_block(
            session,
            article_id=article_id,
            block=blocks[0],
            policy=policy,
            source_run_id=source_run_id,
        )

    summaries: list[dict[str, Any]] = []
    any_persisted = False
    any_failed = False
    for block in blocks:
        summary = _persist_one_article_metadata_block(
            session,
            article_id=article_id,
            block=block,
            policy=policy,
            source_run_id=source_run_id,
        )
        summaries.append(summary)
        any_persisted = any_persisted or bool(summary.get("persisted"))
        if summary.get("status") == "failed":
            any_failed = True

    if any_failed:
        status: ArticleMetadataPersistStatus = "failed"
    elif any_persisted:
        status = "succeeded"
    else:
        status = "skipped"

    return {
        "status": status,
        "persisted": any_persisted,
        "count": len(blocks),
        "meta_types": sorted(
            {
                str(summary.get("meta_type"))
                for summary in summaries
                if isinstance(summary.get("meta_type"), str)
            }
        ),
        "blocks": summaries,
    }
