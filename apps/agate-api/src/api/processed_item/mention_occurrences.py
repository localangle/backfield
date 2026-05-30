"""Mention occurrence helpers for processed-item review (model, overlay, substrate)."""

from __future__ import annotations

import copy
from typing import Any

from backfield_db import SubstrateLocationMentionOccurrence

MAX_MENTION_OCCURRENCES = 50


def _strip_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def occurrence_dict_from_model_mention(
    text: str,
    *,
    order: int,
    is_quote: bool = False,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "mention_text": text,
        "start_char": None,
        "end_char": None,
        "occurrence_order": order,
        "suppressed": False,
        "source_kind": "model",
    }
    if is_quote:
        out["is_quote"] = True
    return out


def occurrences_from_place_dict(place: dict[str, Any]) -> list[dict[str, Any]]:
    """Build occurrence payloads from frozen model ``mentions`` / ``original_text``."""
    raw_mentions = place.get("mentions")
    texts: list[tuple[str, bool]] = []
    if isinstance(raw_mentions, list):
        for i, item in enumerate(raw_mentions):
            if isinstance(item, dict):
                t = _strip_text(item.get("text"))
                if t:
                    texts.append((t, bool(item.get("quote"))))
            elif isinstance(item, str) and item.strip():
                texts.append((item.strip(), False))
    if not texts:
        ot = _strip_text(place.get("original_text"))
        if ot:
            texts = [(ot, False)]
    return [
        occurrence_dict_from_model_mention(t, order=i, is_quote=is_quote)
        for i, (t, is_quote) in enumerate(texts)
    ]


def occurrence_dict_from_db(row: SubstrateLocationMentionOccurrence) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": int(row.id) if row.id is not None else None,
        "mention_text": _strip_text(row.mention_text),
        "start_char": row.start_char,
        "end_char": row.end_char,
        "occurrence_order": row.occurrence_order,
        "suppressed": bool(row.suppressed),
        "source_kind": _strip_text(row.source_kind) or "system_extraction",
    }
    quote_text = _strip_text(row.quote_text)
    if quote_text:
        out["quote_text"] = quote_text
    labels = getattr(row, "labels_json", None)
    if isinstance(labels, list) and "quote" in labels:
        out["is_quote"] = True
    return out


def _occurrence_identity(occ: dict[str, Any]) -> str | None:
    oid = occ.get("id")
    if oid is not None and oid != "":
        return f"id:{oid}"
    cid = occ.get("client_id")
    if isinstance(cid, str) and cid.strip():
        return f"client:{cid.strip()}"
    return None


def normalize_overlay_occurrence(raw: Any, *, default_order: int) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    text = _strip_text(raw.get("mention_text") or raw.get("text"))
    if not text:
        return None
    out: dict[str, Any] = {
        "mention_text": text,
        "start_char": raw.get("start_char"),
        "end_char": raw.get("end_char"),
        "occurrence_order": raw.get("occurrence_order", default_order),
        "suppressed": bool(raw.get("suppressed", False)),
        "source_kind": _strip_text(raw.get("source_kind")) or "user_review",
    }
    if raw.get("id") is not None:
        out["id"] = raw.get("id")
    cid = raw.get("client_id")
    if isinstance(cid, str) and cid.strip():
        out["client_id"] = cid.strip()
    return out


def occurrences_from_overlay_patch(patch: dict[str, Any]) -> list[dict[str, Any]]:
    raw = patch.get("occurrences")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        norm = normalize_overlay_occurrence(item, default_order=i)
        if norm is not None:
            out.append(norm)
    return out


def merge_occurrence_lists(
    base: list[dict[str, Any]],
    overlay: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Overlay wins on matching ``id`` or ``client_id``; append new overlay rows."""
    if not overlay:
        return copy.deepcopy(base)
    merged = copy.deepcopy(base)
    index_by_identity: dict[str, int] = {}
    for i, occ in enumerate(merged):
        ident = _occurrence_identity(occ)
        if ident is not None:
            index_by_identity[ident] = i

    for occ in overlay:
        ident = _occurrence_identity(occ)
        if ident is not None and ident in index_by_identity:
            merged[index_by_identity[ident]] = {**merged[index_by_identity[ident]], **occ}
        else:
            merged.append(copy.deepcopy(occ))
            ident = _occurrence_identity(occ)
            if ident is not None:
                index_by_identity[ident] = len(merged) - 1

    merged.sort(
        key=lambda o: (
            o.get("occurrence_order") if isinstance(o.get("occurrence_order"), int) else 10_000,
            o.get("id") if isinstance(o.get("id"), int) else 10_000,
        )
    )
    return merged


def build_mention_occurrences_for_row(
    *,
    place: dict[str, Any],
    overlay_patch: dict[str, Any] | None,
    db_rows: list[SubstrateLocationMentionOccurrence] | None,
) -> list[dict[str, Any]]:
    """Merge model, substrate DB, and overlay occurrence sources."""
    if db_rows:
        base = [occurrence_dict_from_db(r) for r in db_rows]
        base = [b for b in base if not b.get("suppressed")]
        base.sort(
            key=lambda o: (
                o.get("occurrence_order") if isinstance(o.get("occurrence_order"), int) else 10_000,
                o.get("id") if isinstance(o.get("id"), int) else 10_000,
            )
        )
    else:
        base = occurrences_from_place_dict(place)

    overlay_list: list[dict[str, Any]] = []
    if isinstance(overlay_patch, dict):
        overlay_list = occurrences_from_overlay_patch(overlay_patch)
    loc_overlay = place.get("occurrences")
    if isinstance(loc_overlay, list):
        for i, item in enumerate(loc_overlay):
            norm = normalize_overlay_occurrence(item, default_order=i)
            if norm is not None:
                overlay_list.append(norm)

    return merge_occurrence_lists(base, overlay_list)


def sync_original_text_from_occurrences(
    place: dict[str, Any],
    occurrences: list[dict[str, Any]],
) -> None:
    """Keep ``original_text`` aligned with first active mention for legacy consumers."""
    for occ in occurrences:
        if occ.get("suppressed"):
            continue
        text = _strip_text(occ.get("mention_text"))
        if text:
            place["original_text"] = text
            return


def validate_overlay_occurrences(
    patch: dict[str, Any],
    *,
    article_body_length: int | None,
) -> None:
    from api.processed_item.overlay.validate import OverlayGeometryValidationError

    raw = patch.get("occurrences")
    if raw is None:
        return
    if not isinstance(raw, list):
        raise OverlayGeometryValidationError("occurrences must be an array")
    if len(raw) > MAX_MENTION_OCCURRENCES:
        raise OverlayGeometryValidationError(
            f"occurrences exceeds maximum of {MAX_MENTION_OCCURRENCES}",
        )
    for i, item in enumerate(raw):
        if normalize_overlay_occurrence(item, default_order=i) is None:
            raise OverlayGeometryValidationError(
                "each occurrence must include non-empty mention_text",
            )
        if article_body_length is not None and isinstance(item, dict):
            for key in ("start_char", "end_char"):
                val = item.get(key)
                if val is not None and (
                    not isinstance(val, int)
                    or val < 0
                    or val > article_body_length
                ):
                    raise OverlayGeometryValidationError(
                        "occurrence offsets must be integers within article body length",
                    )
