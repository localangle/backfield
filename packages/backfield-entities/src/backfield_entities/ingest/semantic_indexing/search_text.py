"""Deterministic labeled search text assembly."""

from __future__ import annotations


def append_labeled_line(lines: list[str], label: str, value: str | None) -> None:
    if value is None:
        return
    stripped = value.strip()
    if not stripped:
        return
    lines.append(f"{label}: {stripped}")


def append_joined_line(lines: list[str], label: str, values: list[str] | tuple[str, ...]) -> None:
    cleaned = [value.strip() for value in values if value and value.strip()]
    if not cleaned:
        return
    lines.append(f"{label}: {', '.join(cleaned)}")


def join_search_text(lines: list[str]) -> str:
    return "\n".join(lines).strip()
