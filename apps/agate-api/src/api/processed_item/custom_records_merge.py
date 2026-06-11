"""Normalize and merge custom-record review overlays into run output.

Overlay schema (``overlay.custom_records``, payload-based identity per record type)::

    {
      "custom_records": {
        "<record_type>": {
          "by_key": {
            "<record_key>": {
              "fields": {"<field>": <value>, ...},   # partial field patch
              "mentions": [{"text": "...", "quote": false}, ...]  # full replacement when present
            }
          },
          "removed_keys": ["<record_key>", ...],
          "user_added": [
            {"key": "user_record:<uuid>", "fields": {...}, "mentions": [...],
             "confidence": null, "source": "review"}
          ]
        }
      }
    }

Model records keep their parse-time keys; reviewer-added records carry
``source: "review"`` provenance and are exempt from the mention-grounding
requirement at persist time.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

USER_ADDED_KEY_PREFIX = "user_record:"


@dataclass
class CustomRecordTypeOverlay:
    """Normalized review edits for one record type."""

    by_key: dict[str, dict[str, Any]] = field(default_factory=dict)
    user_added: list[dict[str, Any]] = field(default_factory=list)
    removed_keys: set[str] = field(default_factory=set)

    def has_content(self) -> bool:
        return bool(self.by_key) or bool(self.user_added) or bool(self.removed_keys)


def _is_dict(value: Any) -> bool:
    return isinstance(value, dict)


def _normalize_type_overlay(raw: Any) -> CustomRecordTypeOverlay:
    normalized = CustomRecordTypeOverlay()
    if not _is_dict(raw):
        return normalized

    by_key = raw.get("by_key")
    if _is_dict(by_key):
        for key, patch in by_key.items():
            if isinstance(key, str) and key.strip() and _is_dict(patch):
                normalized.by_key[key] = patch

    user_added = raw.get("user_added")
    if isinstance(user_added, list):
        for row in user_added:
            if not _is_dict(row):
                continue
            key = row.get("key")
            fields = row.get("fields")
            if isinstance(key, str) and key.strip() and _is_dict(fields) and fields:
                normalized.user_added.append(row)

    removed = raw.get("removed_keys")
    if isinstance(removed, list):
        for key in removed:
            if isinstance(key, str) and key.strip():
                normalized.removed_keys.add(key)

    return normalized


def normalize_custom_records_overlay(
    overlay: dict[str, Any] | None,
) -> dict[str, CustomRecordTypeOverlay]:
    """Per-record-type normalized edits from ``overlay.custom_records``."""
    if not _is_dict(overlay):
        return {}
    root = overlay.get("custom_records")
    if not _is_dict(root):
        return {}
    normalized: dict[str, CustomRecordTypeOverlay] = {}
    for record_type, raw in root.items():
        if not isinstance(record_type, str) or not record_type.strip():
            continue
        type_overlay = _normalize_type_overlay(raw)
        if type_overlay.has_content():
            normalized[record_type] = type_overlay
    return normalized


def custom_records_overlay_has_content(overlay: dict[str, Any] | None) -> bool:
    """True when the overlay carries any custom-record review edits."""
    return bool(normalize_custom_records_overlay(overlay))


def _normalize_mentions(raw: Any) -> list[dict[str, Any]]:
    """Custom records support passage mentions only (``quote`` is always false)."""
    if not isinstance(raw, list):
        return []
    normalized: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, str):
            text = entry.strip()
            if text:
                normalized.append({"text": text, "quote": False})
            continue
        if not _is_dict(entry):
            continue
        text = entry.get("text")
        if isinstance(text, str) and text.strip():
            normalized.append({"text": text.strip(), "quote": False})
    return normalized


def _normalized_user_added_record(row: dict[str, Any]) -> dict[str, Any]:
    record = copy.deepcopy(row)
    record["source"] = "review"
    record["mentions"] = _normalize_mentions(record.get("mentions"))
    return record


def _merge_record_with_patch(
    record: dict[str, Any],
    patch: dict[str, Any],
) -> dict[str, Any]:
    merged = copy.deepcopy(record)
    patch_fields = patch.get("fields")
    if _is_dict(patch_fields):
        base_fields = merged.get("fields")
        merged_fields = dict(base_fields) if _is_dict(base_fields) else {}
        merged_fields.update(copy.deepcopy(patch_fields))
        merged["fields"] = merged_fields
    patch_mentions = patch.get("mentions")
    if isinstance(patch_mentions, list):
        merged["mentions"] = _normalize_mentions(patch_mentions)
    return merged


def merge_custom_record_set(
    record_set: dict[str, Any],
    type_overlay: CustomRecordTypeOverlay,
) -> dict[str, Any]:
    """Apply one record type's review edits to its record-set dict."""
    merged_set = copy.deepcopy(record_set)
    raw_records = merged_set.get("records")
    records = raw_records if isinstance(raw_records, list) else []

    merged_records: list[dict[str, Any]] = []
    for record in records:
        if not _is_dict(record):
            continue
        key = record.get("key")
        record_key = key if isinstance(key, str) else ""
        if record_key in type_overlay.removed_keys:
            continue
        patch = type_overlay.by_key.get(record_key)
        if patch is not None:
            merged_records.append(_merge_record_with_patch(record, patch))
        else:
            merged_records.append(copy.deepcopy(record))

    existing_keys = {
        record.get("key") for record in merged_records if isinstance(record.get("key"), str)
    }
    for row in type_overlay.user_added:
        key = row.get("key")
        if key in existing_keys or key in type_overlay.removed_keys:
            continue
        merged_records.append(_normalized_user_added_record(row))

    merged_set["records"] = merged_records
    return merged_set


def merge_custom_records_block(
    block: dict[str, Any],
    overlay: dict[str, Any] | None,
) -> dict[str, Any]:
    """Reviewed ``custom_records`` block: model block + overlay edits per record type."""
    edits = normalize_custom_records_overlay(overlay)
    merged: dict[str, Any] = {}
    for record_type, record_set in block.items():
        if not _is_dict(record_set):
            merged[record_type] = copy.deepcopy(record_set)
            continue
        type_overlay = edits.get(record_type)
        if type_overlay is None:
            merged[record_type] = copy.deepcopy(record_set)
        else:
            merged[record_type] = merge_custom_record_set(record_set, type_overlay)
    return merged


def apply_custom_records_overlay_to_output(
    output: dict[str, Any],
    overlay: dict[str, Any] | None,
) -> None:
    """Replace every ``custom_records`` block in node outputs with the reviewed merge."""
    if not custom_records_overlay_has_content(overlay):
        return
    for payload in output.values():
        if not _is_dict(payload):
            continue
        block = payload.get("custom_records")
        if _is_dict(block):
            payload["custom_records"] = merge_custom_records_block(block, overlay)
        consolidated = payload.get("consolidated")
        if _is_dict(consolidated):
            consolidated_block = consolidated.get("custom_records")
            if _is_dict(consolidated_block):
                consolidated["custom_records"] = merge_custom_records_block(
                    consolidated_block, overlay
                )


def reviewed_custom_records_block(
    output: dict[str, Any] | None,
    overlay: dict[str, Any] | None,
) -> dict[str, Any]:
    """Union of reviewed record sets across node payloads (for substrate re-persist)."""
    union: dict[str, Any] = {}
    if _is_dict(output):
        for payload in output.values():
            if not _is_dict(payload):
                continue
            for block in (
                payload.get("custom_records"),
                payload.get("consolidated", {}).get("custom_records")
                if _is_dict(payload.get("consolidated"))
                else None,
            ):
                if not _is_dict(block):
                    continue
                for record_type, record_set in block.items():
                    if _is_dict(record_set):
                        union[record_type] = record_set
    return merge_custom_records_block(union, overlay)
