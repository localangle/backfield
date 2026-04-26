"""JSON helpers for Stylebook location meta payloads."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException


def parse_meta_json(data_json: Any) -> Any:
    """Normalize DB JSON (dict/list/primitive or legacy string) for API responses."""
    if data_json is None:
        return None
    if isinstance(data_json, (dict, list, str, int, float, bool)):
        return data_json
    return data_json


def validate_meta_json(data: Any) -> None:
    """Ensure value is JSON-serializable (agate-compatible)."""
    try:
        json.dumps(data)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON data: {e!s}") from e
