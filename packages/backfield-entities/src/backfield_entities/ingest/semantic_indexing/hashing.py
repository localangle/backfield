"""Stable source hashes for semantic document builder inputs."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_semantic_source_hash(payload: dict[str, Any]) -> str:
    """Hash persisted builder inputs with stable JSON serialization."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
