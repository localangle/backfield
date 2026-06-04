"""CSV parsing helpers for Stylebook catalog import."""

from __future__ import annotations

import csv
import io

from fastapi import HTTPException


def parse_csv_rows(csv_data: str) -> list[dict[str, str]]:
    """Parse CSV text into row dicts; drops rows that are entirely empty."""
    try:
        reader = csv.DictReader(io.StringIO(csv_data))
        if reader.fieldnames is None:
            raise HTTPException(status_code=400, detail="CSV must include a header row")
        rows: list[dict[str, str]] = []
        for raw in reader:
            normalized = {str(k): (v if v is not None else "") for k, v in raw.items()}
            if any(str(v).strip() for v in normalized.values()):
                rows.append(normalized)
        return rows
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {exc}") from exc


def available_columns_from_rows(rows: list[dict[str, str]]) -> list[str]:
    keys: set[str] = set()
    for row in rows:
        keys.update(row.keys())
    return sorted(keys)


def read_mapped_cell(row: dict[str, str], mappings: dict[str, str], field: str) -> str | None:
    """Read a mapped CSV column for ``field``; fall back to a same-named column."""
    col = (mappings.get(field) or "").strip() or field
    val = row.get(col)
    if val is None:
        return None
    s = str(val).strip()
    return s or None


def parse_public_figure_value(raw: str | None) -> bool:
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    return raw.strip().lower() in ("true", "1", "yes", "y")
