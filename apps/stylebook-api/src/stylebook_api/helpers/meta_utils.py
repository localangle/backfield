"""Helpers for Stylebook typed canonical metadata payloads."""

from __future__ import annotations

from typing import Any

from backfield_entities.catalog.canonical_meta import (
    CanonicalMetaWrite,
    apply_typed_values_to_row,
    meta_row_to_api,
    normalize_meta_type,
)
from fastapi import HTTPException
from pydantic import ValidationError


def parse_meta_write(
    *,
    meta_type: str,
    value_type: str,
    value: Any,
) -> CanonicalMetaWrite:
    """Validate a Stylebook meta write payload or raise HTTP 400."""
    try:
        return CanonicalMetaWrite(meta_type=meta_type, value_type=value_type, value=value)
    except ValidationError as exc:
        message = "; ".join(
            str(err.get("msg") or err) for err in exc.errors()
        ) or "Invalid metadata payload"
        raise HTTPException(status_code=400, detail=message) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def normalize_meta_type_or_400(raw: str) -> str:
    try:
        return normalize_meta_type(raw)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def serialize_meta_row(row: Any) -> dict[str, Any]:
    out = meta_row_to_api(row, include_id=True)
    out["created_at"] = row.created_at.isoformat() if row.created_at else None
    return out


__all__ = [
    "apply_typed_values_to_row",
    "normalize_meta_type_or_400",
    "parse_meta_write",
    "serialize_meta_row",
]
