"""Stable fingerprint for ``substrate_location_cache`` rows (must match ingest)."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

_WS_RE = re.compile(r"\s+")


def normalize_substrate_cache_query(value: str) -> str:
    """Lowercase single-spaced query key; must stay aligned with worker ingest."""
    cleaned = _WS_RE.sub(" ", value.strip()).lower()
    return cleaned


def _sha256_hex(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def substrate_location_cache_query_fingerprint(
    *,
    project_id: int,
    normalized_query: str,
    location_type: str | None,
) -> str:
    """SHA256 of JSON payload; identical to historical worker ``_cache_fingerprint``."""
    return _sha256_hex(
        json.dumps(
            {
                "project_id": project_id,
                "normalized_query": normalized_query,
                "location_type": location_type,
            },
            sort_keys=True,
        )
    )


def substrate_location_cache_fingerprint_for_query_text(
    *,
    project_id: int,
    query_text: str,
    location_type: str | None,
) -> str | None:
    """Normalize ``query_text`` and return fingerprint, or ``None`` if empty after normalize."""
    normalized = normalize_substrate_cache_query(query_text)
    if not normalized:
        return None
    lt = (location_type or "").strip().lower() or None
    return substrate_location_cache_query_fingerprint(
        project_id=project_id,
        normalized_query=normalized,
        location_type=lt,
    )


def substrate_location_cache_fingerprint_payload_for_tests() -> dict[str, Any]:
    """Stable keys used inside the fingerprint JSON (for cross-package assertions)."""
    return {"project_id": int, "normalized_query": str, "location_type": str | None}
