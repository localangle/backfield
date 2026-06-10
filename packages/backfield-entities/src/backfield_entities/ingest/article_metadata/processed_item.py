"""Article metadata rows for processed-item review."""

from __future__ import annotations

from typing import Any, Literal

from backfield_db import SubstrateArticleMeta
from sqlmodel import Session, select

ArticleMetaRowSource = Literal["model", "review"]


def normalize_article_meta_overlay(overlay: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Return ``meta_row_id`` → patch dict (currently ``category`` only)."""
    if not overlay or not isinstance(overlay, dict):
        return {}
    root = overlay.get("article_meta")
    if not isinstance(root, dict):
        return {}
    by_id = root.get("by_id")
    if not isinstance(by_id, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for raw_id, patch in by_id.items():
        if not isinstance(patch, dict):
            continue
        key = str(raw_id).strip()
        if not key:
            continue
        category = patch.get("category")
        if isinstance(category, str) and category.strip():
            normalized: dict[str, Any] = {"category": category.strip()}
            meta_type = patch.get("meta_type")
            if isinstance(meta_type, str) and meta_type.strip():
                normalized["meta_type"] = meta_type.strip()
            out[key] = normalized
    return out


def article_meta_overlay_has_content(overlay: dict[str, Any] | None) -> bool:
    return bool(normalize_article_meta_overlay(overlay))


def _row_to_dict(row: SubstrateArticleMeta, *, source: ArticleMetaRowSource) -> dict[str, Any]:
    return {
        "id": int(row.id),  # type: ignore[arg-type]
        "meta_type": row.meta_type,
        "category": row.category,
        "rationale": row.rationale,
        "confidence": float(row.confidence),
        "prompt_preset": row.prompt_preset,
        "updated_at": row.updated_at,
        "source": source,
    }


def load_substrate_article_meta_rows(
    session: Session,
    *,
    article_id: int,
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(SubstrateArticleMeta)
        .where(SubstrateArticleMeta.article_id == article_id)
        .order_by(SubstrateArticleMeta.meta_type, SubstrateArticleMeta.id)
    ).all()
    return [_row_to_dict(row, source="model") for row in rows]


def merge_article_meta_with_overlay(
    rows: list[dict[str, Any]],
    overlay_patches_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    if not overlay_patches_by_id:
        return [dict(row) for row in rows]
    merged: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        row_id = str(copy.get("id"))
        patch = overlay_patches_by_id.get(row_id)
        if patch and isinstance(patch.get("category"), str):
            copy["category"] = patch["category"]
            copy["source"] = "review"
        merged.append(copy)
    return merged


def build_processed_item_article_meta_rows(
    session: Session | None,
    *,
    article_id: int | None,
    overlay: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if session is None or article_id is None:
        return []
    substrate_rows = load_substrate_article_meta_rows(session, article_id=article_id)
    patches = normalize_article_meta_overlay(overlay)
    return merge_article_meta_with_overlay(substrate_rows, patches)


def apply_merged_article_meta_to_output(
    output: dict[str, Any],
    merged_rows: list[dict[str, Any]],
) -> None:
    """Patch ``article_metadata.category`` in node outputs when ``meta_type`` matches."""
    if not merged_rows:
        return
    by_type = {
        str(row["meta_type"]): row
        for row in merged_rows
        if isinstance(row.get("meta_type"), str)
    }
    if not by_type:
        return

    def patch_block(block: dict[str, Any]) -> None:
        meta_type = block.get("meta_type")
        if not isinstance(meta_type, str):
            return
        merged = by_type.get(meta_type)
        if not merged:
            return
        category = merged.get("category")
        if isinstance(category, str) and category.strip():
            block["category"] = category.strip()

    for payload in output.values():
        if not isinstance(payload, dict):
            continue
        direct = payload.get("article_metadata")
        if isinstance(direct, dict):
            patch_block(direct)
        consolidated = payload.get("consolidated")
        if isinstance(consolidated, dict):
            nested = consolidated.get("article_metadata")
            if isinstance(nested, dict):
                patch_block(nested)

    stylebook = output.get("stylebook_output")
    if isinstance(stylebook, dict):
        nested = stylebook.get("article_metadata")
        if isinstance(nested, dict):
            patch_block(nested)


def article_meta_review_rows_from_overlay(
    overlay: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Rows derived from overlay patches for reviewed-output materialization."""
    rows: list[dict[str, Any]] = []
    for patch in normalize_article_meta_overlay(overlay).values():
        meta_type = patch.get("meta_type")
        category = patch.get("category")
        if isinstance(meta_type, str) and isinstance(category, str):
            rows.append({"meta_type": meta_type, "category": category})
    return rows
