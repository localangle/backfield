"""Parse high-school schedule scoreboard ``Team A at Team B`` lines."""

from __future__ import annotations

import re

SCHEDULE_AT_LINE_RE = re.compile(
    r"^\s*(?P<away>.+?)\s+at\s+(?P<home>.+?)\s*$",
    flags=re.IGNORECASE,
)


def extract_schedule_matchups(article_text: str) -> list[tuple[str, str]]:
    """Return ``(away, home)`` school tokens from schedule lines."""
    pairs: list[tuple[str, str]] = []
    for line in article_text.splitlines():
        stripped = line.strip()
        if not stripped or "(" in stripped or ")" in stripped:
            continue
        match = SCHEDULE_AT_LINE_RE.match(stripped)
        if match is None:
            continue
        away = match.group("away").strip()
        home = match.group("home").strip()
        if away and home:
            pairs.append((away, home))
    return pairs


def find_schedule_line_for_school(article_text: str, school_name: str) -> str | None:
    """Return the single ``Away at Home`` line that mentions ``school_name``."""
    primary = (school_name or "").split(",")[0].strip()
    if not primary:
        return None
    primary_lower = primary.lower()
    for away, home in extract_schedule_matchups(article_text):
        if primary_lower == away.lower() or primary_lower == home.lower():
            return f"{away} at {home}"
    return None
