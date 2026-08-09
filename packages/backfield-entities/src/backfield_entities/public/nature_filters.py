"""Helpers for repeatable public-API nature filters (OR / IN semantics)."""

from __future__ import annotations


def normalize_natures(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    """Strip, drop empties, and dedupe while preserving order."""
    if not values:
        return ()
    seen: set[str] = set()
    out: list[str] = []
    for raw in values:
        token = str(raw or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
    return tuple(out)


def postgres_natures_in_filter(
    natures: tuple[str, ...],
    bind: dict[str, object],
    *,
    column_sql: str,
    bind_prefix: str = "nature",
) -> str:
    """Return ``AND <column> IN (...)`` SQL, mutating ``bind`` with placeholders."""
    normalized = normalize_natures(natures)
    if not normalized:
        return ""
    placeholders = ", ".join(f":{bind_prefix}_{index}" for index in range(len(normalized)))
    for index, value in enumerate(normalized):
        bind[f"{bind_prefix}_{index}"] = value
    return f"AND {column_sql} IN ({placeholders})"
