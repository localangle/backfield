"""Display-name slug helpers for seeding and bootstrap."""

from __future__ import annotations

import re

_MAX_SLUG_LEN = 100


def slugify_display_name(name: str, *, fallback: str) -> str:
    """Lowercase ASCII slug from a display name (hyphenated)."""
    s = name.lower().strip().replace(" ", "-")
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        s = fallback
    if len(s) > _MAX_SLUG_LEN:
        s = s[:_MAX_SLUG_LEN].rstrip("-") or fallback
    return s
