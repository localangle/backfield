"""Article context snippets for occurrence-level semantic documents."""

from __future__ import annotations

DEFAULT_CONTEXT_CHARS_BEFORE = 300
DEFAULT_CONTEXT_CHARS_AFTER = 300


def extract_article_context_snippet(
    article_text: str,
    *,
    start_char: int | None,
    end_char: int | None,
    chars_before: int = DEFAULT_CONTEXT_CHARS_BEFORE,
    chars_after: int = DEFAULT_CONTEXT_CHARS_AFTER,
) -> str | None:
    """Return nearby article text around occurrence character offsets."""
    if start_char is None or end_char is None:
        return None
    if start_char < 0 or end_char < start_char:
        return None
    text = article_text or ""
    if not text:
        return None
    start = max(0, start_char - chars_before)
    end = min(len(text), end_char + chars_after)
    snippet = text[start:end].strip()
    return snippet or None
