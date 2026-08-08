"""Ownership filtering and exact-field merge for chunked Custom Extract."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from agate_nodes.extraction.grounding import ChunkCandidate, union_mention_texts


def _fields_fingerprint(fields: dict[str, Any]) -> str:
    return json.dumps(fields, sort_keys=True, default=str)


def _mention_texts(record: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for mention in record.get("mentions") or []:
        if isinstance(mention, dict):
            text = mention.get("text")
            if isinstance(text, str) and text.strip():
                out.append(text.strip())
    return out


def _merge_records(base: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    mention_texts = union_mention_texts(_mention_texts(merged), _mention_texts(other))
    merged["mentions"] = [{"text": text} for text in mention_texts]
    left_conf = merged.get("confidence")
    right_conf = other.get("confidence")
    if isinstance(left_conf, (int, float)) and isinstance(right_conf, (int, float)):
        merged["confidence"] = max(float(left_conf), float(right_conf))
    elif right_conf is not None and left_conf is None:
        merged["confidence"] = right_conf
    return merged


def stitch_custom_candidates(
    candidates: list[ChunkCandidate[dict[str, Any]]],
    *,
    record_type: str,
) -> list[dict[str, Any]]:
    """Exact normalized-field merge for owned custom records; regenerate stable keys."""
    owned = [c for c in candidates if c.owned and isinstance(c.payload, dict)]
    clusters: list[dict[str, Any]] = []
    by_fingerprint: dict[str, int] = {}

    for candidate in sorted(owned, key=lambda c: (c.evidence.start if c.evidence else 0)):
        record = dict(candidate.payload)
        fields = record.get("fields")
        if not isinstance(fields, dict):
            continue
        fingerprint = _fields_fingerprint(fields)
        existing = by_fingerprint.get(fingerprint)
        if existing is not None:
            clusters[existing] = _merge_records(clusters[existing], record)
            continue
        by_fingerprint[fingerprint] = len(clusters)
        clusters.append(record)

    used_keys: set[str] = set()
    finalized: list[dict[str, Any]] = []
    for record in clusters:
        fields = record.get("fields") if isinstance(record.get("fields"), dict) else {}
        digest = hashlib.sha1(
            f"{record_type}:{_fields_fingerprint(fields)}".encode()
        ).hexdigest()[:12]
        key = f"{record_type}_{digest}"
        suffix = 2
        while key in used_keys:
            key = f"{record_type}_{digest}_{suffix}"
            suffix += 1
        used_keys.add(key)
        out = dict(record)
        out["key"] = key
        finalized.append(out)
    return finalized
