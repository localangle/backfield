"""Compose the string embedded for a full article."""

from __future__ import annotations

from typing import Any

# Top-level string fields included after ``text`` and ``headline`` when non-empty.
_SUPPORTING_STRING_FIELDS: tuple[str, ...] = ("url", "author", "byline", "publication")


def compose_article_embed_text(flattened: dict[str, Any]) -> str:
    """Build one embedding input from upstream article-shaped payload."""
    text = flattened.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(
            "Embed Text requires non-empty upstream text. "
            "Connect a node that provides a text field."
        )

    parts: list[str] = []

    headline = flattened.get("headline")
    if isinstance(headline, str) and headline.strip():
        parts.append(headline.strip())

    parts.append(text.strip())

    for key in _SUPPORTING_STRING_FIELDS:
        value = flattened.get(key)
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())

    for key, value in flattened.items():
        if not key.startswith("meta_"):
            continue
        if isinstance(value, str) and value.strip():
            parts.append(value.strip())
        elif isinstance(value, dict):
            for nested in value.values():
                if isinstance(nested, str) and nested.strip():
                    parts.append(nested.strip())

    return "\n\n".join(parts)
