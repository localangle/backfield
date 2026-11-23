"""Instance-level settings for the cleanup API, read from the environment."""

from __future__ import annotations

import os

DEFAULT_SNIPPET_MAX_CHARS = 500


def snippet_max_chars() -> int:
    """Longest article snippet an evidence response may carry; 0 turns snippets off.

    Set with `BACKFIELD_CLEANUP_SNIPPET_MAX_CHARS`. An unset or invalid value uses the default.
    """
    raw = os.getenv("BACKFIELD_CLEANUP_SNIPPET_MAX_CHARS", "").strip()
    if not raw:
        return DEFAULT_SNIPPET_MAX_CHARS
    try:
        return max(int(raw), 0)
    except ValueError:
        return DEFAULT_SNIPPET_MAX_CHARS
