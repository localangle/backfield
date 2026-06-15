"""Article metadata rows for processed-item review."""

from __future__ import annotations

import copy
import json
from typing import Any, Literal

from backfield_db import SubstrateArticleMeta
from sqlmodel import Session, select

ArticleMetaRowSource = Literal["model", "review"]

USER_META_ROW_ID_FLOOR = -900_000
REVIEW_ADDED_RATIONALE = "Added during review."
REVIEW_ADDED_CONFIDENCE = 1.0


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


def normalize_article_meta_removed_ids(overlay: dict[str, Any] | None) -> set[str]:
    """Return removed article-meta row ids from overlay."""
    if not overlay or not isinstance(overlay, dict):
        return set()
    root = overlay.get("article_meta")
    if not isinstance(root, dict):
        return set()
    removed = root.get("removed_ids")
    if not isinstance(removed, list):
        return set()
    out: set[str] = set()
    for raw in removed:
        key = str(raw).strip()
        if key:
            out.add(key)
    return out


def normalize_article_meta_removed_meta_types(overlay: dict[str, Any] | None) -> set[str]:
    """Return removed article-meta preset types from overlay."""
    if not overlay or not isinstance(overlay, dict):
        return set()
    root = overlay.get("article_meta")
    if not isinstance(root, dict):
        return set()
    removed = root.get("removed_meta_types")
    if not isinstance(removed, list):
        return set()
    out: set[str] = set()
    for raw in removed:
        key = str(raw).strip()
        if key:
            out.add(key)
    return out


def article_meta_overlay_has_content(overlay: dict[str, Any] | None) -> bool:
    if normalize_article_meta_overlay(overlay):
        return True
    if normalize_article_meta_removed_ids(overlay):
        return True
    if normalize_article_meta_user_added(overlay):
        return True
    return bool(normalize_article_meta_removed_meta_types(overlay))


def normalize_article_meta_user_added(overlay: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Reviewer-added metadata rows from ``article_meta.user_added``."""
    if not overlay or not isinstance(overlay, dict):
        return []
    root = overlay.get("article_meta")
    if not isinstance(root, dict):
        return []
    raw = root.get("user_added")
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        meta_type = str(entry.get("meta_type") or "").strip()
        category = str(entry.get("category") or "").strip()
        if not meta_type or not category:
            continue
        raw_id = entry.get("id")
        if not isinstance(raw_id, int):
            continue
        rationale = str(entry.get("rationale") or REVIEW_ADDED_RATIONALE).strip()
        confidence = _confidence_or_none(entry.get("confidence"))
        if confidence is None:
            confidence = REVIEW_ADDED_CONFIDENCE
        prompt_preset_raw = entry.get("prompt_preset")
        prompt_preset = (
            prompt_preset_raw.strip()
            if isinstance(prompt_preset_raw, str) and prompt_preset_raw.strip()
            else meta_type
        )
        rows.append(
            {
                "id": raw_id,
                "meta_type": meta_type,
                "category": category,
                "rationale": rationale,
                "confidence": confidence,
                "prompt_preset": prompt_preset,
                "updated_at": None,
                "source": "review",
            }
        )
    return rows


def allocate_user_meta_row_id(
    *,
    existing_rows: list[dict[str, Any]],
    user_added: list[dict[str, Any]],
) -> int:
    """Next synthetic id for a reviewer-added metadata row (below model ids)."""
    floor = USER_META_ROW_ID_FLOOR
    for row in [*existing_rows, *user_added]:
        raw_id = row.get("id")
        if isinstance(raw_id, int) and raw_id < floor:
            floor = raw_id
    return floor - 1


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


def _confidence_or_none(raw: Any) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value < 0.0 or value > 1.0:
        return None
    return value


def _rows_from_metadata_block(
    block: dict[str, Any],
    *,
    synthetic_id_base: int,
) -> list[dict[str, Any]]:
    meta_type = str(block.get("meta_type") or "").strip()
    if not meta_type:
        return []

    prompt_preset_raw = block.get("prompt_preset")
    prompt_preset = (
        prompt_preset_raw.strip()
        if isinstance(prompt_preset_raw, str) and prompt_preset_raw.strip()
        else None
    )

    for list_key in ("topics", "subjects", "needs"):
        raw_items = block.get(list_key)
        if not isinstance(raw_items, list):
            continue
        rows: list[dict[str, Any]] = []
        for idx, entry in enumerate(raw_items):
            if not isinstance(entry, dict):
                continue
            category = str(entry.get("category") or block.get("category") or "").strip()
            rationale = str(entry.get("rationale") or block.get("rationale") or "").strip()
            confidence = _confidence_or_none(entry.get("confidence", block.get("confidence")))
            if not category or not rationale or confidence is None:
                continue
            rows.append(
                {
                    "id": synthetic_id_base - idx,
                    "meta_type": meta_type,
                    "category": category,
                    "rationale": rationale,
                    "confidence": confidence,
                    "prompt_preset": prompt_preset,
                    "updated_at": None,
                    "source": "model",
                }
            )
        if rows:
            return rows

    category = str(block.get("category") or "").strip()
    rationale = str(block.get("rationale") or "").strip()
    confidence = _confidence_or_none(block.get("confidence"))
    if not category or not rationale or confidence is None:
        return []
    return [
        {
            "id": synthetic_id_base,
            "meta_type": meta_type,
            "category": category,
            "rationale": rationale,
            "confidence": confidence,
            "prompt_preset": prompt_preset,
            "updated_at": None,
            "source": "model",
        }
    ]


def collect_article_metadata_blocks_from_output(
    output: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Collect ``article_metadata`` blocks from a processed-item run payload."""
    if not output or not isinstance(output, dict):
        return []

    blocks: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_block(raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        if not str(raw.get("meta_type") or "").strip():
            return
        key = json.dumps(raw, sort_keys=True, default=str)
        if key in seen:
            return
        seen.add(key)
        blocks.append(raw)

    stylebook = output.get("stylebook_output")
    if isinstance(stylebook, dict):
        all_raw = stylebook.get("article_metadata_all")
        if isinstance(all_raw, list):
            for entry in all_raw:
                add_block(entry)
        add_block(stylebook.get("article_metadata"))

    json_output = output.get("json_output")
    if isinstance(json_output, dict):
        consolidated = json_output.get("consolidated")
        if isinstance(consolidated, dict):
            all_raw = consolidated.get("article_metadata_all")
            if isinstance(all_raw, list):
                for entry in all_raw:
                    add_block(entry)
            add_block(consolidated.get("article_metadata"))

    for payload in output.values():
        if not isinstance(payload, dict):
            continue
        add_block(payload.get("article_metadata"))

    return blocks


def merge_article_meta_with_overlay(
    rows: list[dict[str, Any]],
    overlay_patches_by_id: dict[str, dict[str, Any]],
    *,
    removed_ids: set[str] | None = None,
    removed_meta_types: set[str] | None = None,
) -> list[dict[str, Any]]:
    removed = removed_ids or set()
    removed_types = removed_meta_types or set()
    patches_by_meta_type: dict[str, dict[str, Any]] = {}
    for patch in overlay_patches_by_id.values():
        meta_type = patch.get("meta_type")
        if isinstance(meta_type, str) and meta_type.strip():
            patches_by_meta_type[meta_type.strip()] = patch
    merged: list[dict[str, Any]] = []
    for row in rows:
        row_id = str(row.get("id"))
        meta_type = str(row.get("meta_type") or "")
        if row_id in removed or meta_type in removed_types:
            continue
        copy = dict(row)
        patch = overlay_patches_by_id.get(row_id)
        if patch is None and meta_type:
            patch = patches_by_meta_type.get(meta_type)
        if patch and isinstance(patch.get("category"), str):
            copy["category"] = patch["category"]
            copy["source"] = "review"
        merged.append(copy)
    return merged


def _append_user_added_article_meta_rows(
    merged: list[dict[str, Any]],
    *,
    overlay_patches_by_id: dict[str, dict[str, Any]],
    user_added: list[dict[str, Any]],
    removed_ids: set[str],
) -> list[dict[str, Any]]:
    patches_by_meta_type: dict[str, dict[str, Any]] = {}
    for patch in overlay_patches_by_id.values():
        meta_type = patch.get("meta_type")
        if isinstance(meta_type, str) and meta_type.strip():
            patches_by_meta_type[meta_type.strip()] = patch
    existing_ids = {row.get("id") for row in merged}
    for row in user_added:
        row_id = str(row.get("id"))
        if row_id in removed_ids or row.get("id") in existing_ids:
            continue
        copy = dict(row)
        patch = overlay_patches_by_id.get(row_id)
        meta_type = str(copy.get("meta_type") or "")
        if patch is None and meta_type:
            patch = patches_by_meta_type.get(meta_type)
        if patch and isinstance(patch.get("category"), str):
            copy["category"] = patch["category"]
        merged.append(copy)
    return merged


def build_processed_item_article_meta_rows(
    session: Session | None,
    *,
    article_id: int | None,
    overlay: dict[str, Any] | None,
    output: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    patches = normalize_article_meta_overlay(overlay)
    removed_ids = normalize_article_meta_removed_ids(overlay)
    removed_meta_types = normalize_article_meta_removed_meta_types(overlay)
    user_added = normalize_article_meta_user_added(overlay)
    substrate_rows: list[dict[str, Any]] = []
    if session is not None and article_id is not None:
        substrate_rows = load_substrate_article_meta_rows(session, article_id=article_id)
    if substrate_rows:
        merged = merge_article_meta_with_overlay(
            substrate_rows,
            patches,
            removed_ids=removed_ids,
            removed_meta_types=removed_meta_types,
        )
        return _append_user_added_article_meta_rows(
            merged,
            overlay_patches_by_id=patches,
            user_added=user_added,
            removed_ids=removed_ids,
        )

    model_rows: list[dict[str, Any]] = []
    for index, block in enumerate(collect_article_metadata_blocks_from_output(output)):
        model_rows.extend(_rows_from_metadata_block(block, synthetic_id_base=-(index + 1) * 1000))
    merged = merge_article_meta_with_overlay(
        model_rows,
        patches,
        removed_ids=removed_ids,
        removed_meta_types=removed_meta_types,
    )
    return _append_user_added_article_meta_rows(
        merged,
        overlay_patches_by_id=patches,
        user_added=user_added,
        removed_ids=removed_ids,
    )


def _metadata_block_from_row(row: dict[str, Any]) -> dict[str, Any]:
    meta_type = str(row.get("meta_type") or "").strip()
    category = str(row.get("category") or "").strip()
    rationale = str(row.get("rationale") or REVIEW_ADDED_RATIONALE).strip()
    confidence = _confidence_or_none(row.get("confidence"))
    if confidence is None:
        confidence = REVIEW_ADDED_CONFIDENCE
    prompt_preset_raw = row.get("prompt_preset")
    prompt_preset = (
        prompt_preset_raw.strip()
        if isinstance(prompt_preset_raw, str) and prompt_preset_raw.strip()
        else meta_type
    )
    return {
        "meta_type": meta_type,
        "category": category,
        "rationale": rationale,
        "confidence": confidence,
        "prompt_preset": prompt_preset,
    }


def _upsert_metadata_block_in_payload(payload: dict[str, Any], block: dict[str, Any]) -> bool:
    meta_type = str(block.get("meta_type") or "").strip()
    if not meta_type:
        return False

    def upsert_existing(existing: dict[str, Any]) -> bool:
        if str(existing.get("meta_type") or "").strip() != meta_type:
            return False
        existing["category"] = block["category"]
        existing["rationale"] = block["rationale"]
        existing["confidence"] = block["confidence"]
        if block.get("prompt_preset"):
            existing["prompt_preset"] = block["prompt_preset"]
        return True

    direct = payload.get("article_metadata")
    if isinstance(direct, dict) and upsert_existing(direct):
        return True

    consolidated = payload.get("consolidated")
    if isinstance(consolidated, dict):
        nested = consolidated.get("article_metadata")
        if isinstance(nested, dict) and upsert_existing(nested):
            return True
        all_raw = consolidated.get("article_metadata_all")
        if isinstance(all_raw, list):
            for entry in all_raw:
                if isinstance(entry, dict) and upsert_existing(entry):
                    return True

    return False


def _insert_metadata_block_in_payload(payload: dict[str, Any], block: dict[str, Any]) -> None:
    consolidated = payload.get("consolidated")
    if isinstance(consolidated, dict):
        all_raw = consolidated.get("article_metadata_all")
        block_copy = copy.deepcopy(block)
        if isinstance(all_raw, list):
            all_raw.append(block_copy)
            return
        existing = consolidated.get("article_metadata")
        if isinstance(existing, dict):
            consolidated["article_metadata_all"] = [existing, block_copy]
            consolidated.pop("article_metadata", None)
            return
        consolidated["article_metadata"] = block_copy
        return

    if payload.get("article_metadata") is None:
        payload["article_metadata"] = copy.deepcopy(block)


def apply_merged_article_meta_rows_to_output(
    output: dict[str, Any],
    merged_rows: list[dict[str, Any]],
) -> None:
    """Upsert reviewed metadata rows into every ``article_metadata`` block."""
    if not merged_rows:
        return
    blocks = [_metadata_block_from_row(row) for row in merged_rows if row.get("meta_type")]
    if not blocks:
        return

    payloads: list[dict[str, Any]] = []
    for payload in output.values():
        if isinstance(payload, dict):
            payloads.append(payload)
    stylebook = output.get("stylebook_output")
    if isinstance(stylebook, dict):
        payloads.append(stylebook)

    for block in blocks:
        inserted = False
        for payload in payloads:
            if _upsert_metadata_block_in_payload(payload, block):
                inserted = True
        if inserted:
            continue
        json_payload = output.get("json_output")
        if isinstance(json_payload, dict):
            _insert_metadata_block_in_payload(json_payload, block)
        elif isinstance(stylebook, dict):
            _insert_metadata_block_in_payload(stylebook, block)


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

    def patch_payload(payload: dict[str, Any]) -> None:
        direct = payload.get("article_metadata")
        if isinstance(direct, dict):
            patch_block(direct)
        consolidated = payload.get("consolidated")
        if isinstance(consolidated, dict):
            nested = consolidated.get("article_metadata")
            if isinstance(nested, dict):
                patch_block(nested)
            all_raw = consolidated.get("article_metadata_all")
            if isinstance(all_raw, list):
                for block in all_raw:
                    if isinstance(block, dict):
                        patch_block(block)

    for payload in output.values():
        if isinstance(payload, dict):
            patch_payload(payload)

    stylebook = output.get("stylebook_output")
    if isinstance(stylebook, dict):
        patch_payload(stylebook)


def _detach_metadata_block_from_output(output: dict[str, Any], block: dict[str, Any]) -> None:
    def scrub_payload(payload: dict[str, Any]) -> None:
        if payload.get("article_metadata") is block:
            payload.pop("article_metadata", None)
        consolidated = payload.get("consolidated")
        if not isinstance(consolidated, dict):
            return
        if consolidated.get("article_metadata") is block:
            consolidated.pop("article_metadata", None)
        all_raw = consolidated.get("article_metadata_all")
        if isinstance(all_raw, list):
            consolidated["article_metadata_all"] = [
                entry for entry in all_raw if entry is not block
            ]

    for payload in output.values():
        if isinstance(payload, dict):
            scrub_payload(payload)

    stylebook = output.get("stylebook_output")
    if isinstance(stylebook, dict):
        scrub_payload(stylebook)


def _remove_list_entries_from_metadata_block(
    block: dict[str, Any],
    *,
    removed_row_ids: set[int],
    synthetic_id_base: int,
) -> None:
    for list_key in ("topics", "subjects", "needs"):
        items = block.get(list_key)
        if not isinstance(items, list):
            continue
        kept: list[Any] = []
        for idx, entry in enumerate(items):
            row_id = synthetic_id_base - idx
            if row_id not in removed_row_ids:
                kept.append(entry)
        if kept:
            block[list_key] = kept
        else:
            block.pop(list_key, None)


def remove_article_meta_from_output(
    output: dict[str, Any],
    *,
    removed_row_ids: set[int],
    removed_meta_types: set[str] | None = None,
) -> None:
    """Drop removed article-metadata rows from node outputs for reviewed materialization."""
    removed_types = removed_meta_types or set()
    if not removed_row_ids and not removed_types:
        return

    blocks = list(collect_article_metadata_blocks_from_output(output))
    for block_index, block in enumerate(blocks):
        if not isinstance(block, dict):
            continue
        meta_type = str(block.get("meta_type") or "")
        if meta_type in removed_types:
            _detach_metadata_block_from_output(output, block)
            continue
        synthetic_id_base = -(block_index + 1) * 1000
        rows = _rows_from_metadata_block(block, synthetic_id_base=synthetic_id_base)
        row_ids = {int(row["id"]) for row in rows}
        if not row_ids.intersection(removed_row_ids):
            continue
        remaining = row_ids - removed_row_ids
        if not remaining:
            _detach_metadata_block_from_output(output, block)
            continue
        _remove_list_entries_from_metadata_block(
            block,
            removed_row_ids=removed_row_ids,
            synthetic_id_base=synthetic_id_base,
        )
        if not _rows_from_metadata_block(block, synthetic_id_base=synthetic_id_base):
            _detach_metadata_block_from_output(output, block)


def removed_article_meta_row_ids_from_overlay(overlay: dict[str, Any] | None) -> set[int]:
    ids: set[int] = set()
    for raw in normalize_article_meta_removed_ids(overlay):
        try:
            ids.add(int(raw))
        except ValueError:
            continue
    return ids


def removed_article_meta_types_from_overlay(overlay: dict[str, Any] | None) -> set[str]:
    return normalize_article_meta_removed_meta_types(overlay)


def find_article_meta_row_by_id(
    session: Session | None,
    *,
    article_id: int | None,
    output: dict[str, Any] | None,
    overlay: dict[str, Any] | None,
    meta_row_id: int,
) -> dict[str, Any] | None:
    """Resolve one merged article-meta row by synthetic or substrate id."""
    rows = build_processed_item_article_meta_rows(
        session,
        article_id=article_id,
        overlay=overlay,
        output=output,
    )
    for row in rows:
        if row.get("id") == meta_row_id:
            return row
    return None


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
