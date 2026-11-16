"""Compose the string embedded for a full article."""

from __future__ import annotations

from typing import Any

from backfield_ai.token_budget import count_tokens, truncate_to_token_limit

# Top-level string fields included after ``text`` and ``headline`` when non-empty.
_SUPPORTING_STRING_FIELDS: tuple[str, ...] = ("url", "author", "byline", "publication")

# ``text-embedding-3-small`` rejects inputs over 8,192 tokens. The article input is cut at 8,000
# real tokens, leaving headroom for separators and small tokenizer differences.
DEFAULT_EMBED_INPUT_TOKEN_BUDGET = 8000

_PART_SEPARATOR = "\n\n"


def compose_article_embed_text(
    flattened: dict[str, Any],
    *,
    max_input_tokens: int = DEFAULT_EMBED_INPUT_TOKEN_BUDGET,
) -> tuple[str, bool]:
    """Build one embedding input from upstream article-shaped payload.

    Returns ``(embedded_text, truncated)``. The whole input stays within ``max_input_tokens``
    real tokens. Only the article body is shortened (the headline and metadata are kept), so a
    very long article is embedded from its opening text.
    """
    text = flattened.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError(
            "Embed Text requires non-empty upstream text. "
            "Connect a node that provides a text field."
        )

    headline_parts: list[str] = []
    headline = flattened.get("headline")
    if isinstance(headline, str) and headline.strip():
        headline_parts.append(headline.strip())

    metadata_parts = _metadata_parts(flattened)

    other_parts = headline_parts + metadata_parts
    overhead_tokens = count_tokens(_PART_SEPARATOR.join(other_parts)) + count_tokens(
        _PART_SEPARATOR
    ) * len(other_parts)
    body_budget = max_input_tokens - overhead_tokens
    body, body_truncated = truncate_to_token_limit(text.strip(), body_budget)

    composed = _PART_SEPARATOR.join([*headline_parts, body, *metadata_parts])
    # Final guard: metadata alone could be large, or tokenization could differ across joins.
    composed, composed_truncated = truncate_to_token_limit(composed, max_input_tokens)
    return composed, body_truncated or composed_truncated


def _metadata_parts(flattened: dict[str, Any]) -> list[str]:
    parts: list[str] = []
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
    return parts
