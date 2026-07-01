"""Parse compact array PlaceExtract model output into location dicts."""

from __future__ import annotations

import logging
from typing import Any

from agate_nodes.place_extract.compact_codes import expand_row_enum_fields

logger = logging.getLogger(__name__)

ROLE_ARRAY_FIELDS = (
    "location",
    "type",
    "nature",
    "address_place_kind",
    "description",
    "geocode_hints",
)


def _cell_to_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def row_to_entry(row: list[Any], *, expand_codes: bool = True) -> dict[str, str]:
    """Convert one array row into a compact location dict."""
    cells = list(row)
    if len(cells) < len(ROLE_ARRAY_FIELDS):
        logger.warning(
            "[PlaceExtract] compact row has %d fields, expected %d; padding with empty strings",
            len(cells),
            len(ROLE_ARRAY_FIELDS),
        )
        cells.extend([""] * (len(ROLE_ARRAY_FIELDS) - len(cells)))
    elif len(cells) > len(ROLE_ARRAY_FIELDS):
        cells = cells[: len(ROLE_ARRAY_FIELDS)]

    entry: dict[str, str] = {}
    for index, key in enumerate(ROLE_ARRAY_FIELDS):
        entry[key] = _cell_to_str(cells[index])
    if expand_codes:
        return expand_row_enum_fields(entry)
    return entry


def parse_compact_location_rows(
    rows: list[Any],
    *,
    expand_codes: bool = True,
) -> list[dict[str, Any]]:
    """Parse a locations array of fixed-width rows or pass through object rows."""
    parsed: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            entry = expand_row_enum_fields(row) if expand_codes else dict(row)
            parsed.append(entry)
            continue
        if not isinstance(row, list):
            raise ValueError(f"Each location row must be an array or object, got {type(row).__name__}")
        parsed.append(row_to_entry(row, expand_codes=expand_codes))
    return parsed


def parse_compact_locations(
    response_data: dict[str, Any],
    *,
    expand_codes: bool = True,
) -> list[dict[str, Any]]:
    """Parse ``{"locations": [[...], ...]}`` compact array JSON."""
    locations = response_data.get("locations")
    if locations is None:
        raise ValueError("Compact array response JSON must contain a locations array")
    if not isinstance(locations, list):
        raise ValueError("Compact array response locations must be an array")
    return parse_compact_location_rows(locations, expand_codes=expand_codes)


def is_compact_array_entry(entry: dict[str, Any]) -> bool:
    """True when the entry is a compact row dict that still needs Python expansion."""
    if "components" in entry or "original_text" in entry or "mentions" in entry:
        return False
    location = entry.get("location")
    entry_type = entry.get("type")
    return isinstance(location, str) and isinstance(entry_type, str)
