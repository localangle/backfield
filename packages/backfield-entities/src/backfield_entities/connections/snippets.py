"""Snippet helpers for connection inference prompts."""

from __future__ import annotations

from backfield_entities.connections.caps import MAX_SNIPPET_CHARS
from backfield_entities.connections.match_tokens import entity_comention_tokens
from backfield_entities.connections.types import LinkedEntitySnapshot


def _trim(text: str) -> str:
    stripped = text.strip()
    if len(stripped) <= MAX_SNIPPET_CHARS:
        return stripped
    return stripped[:MAX_SNIPPET_CHARS] + "..."


def collect_pair_snippets(
    *,
    from_entities: tuple[LinkedEntitySnapshot, ...],
    to_entities: tuple[LinkedEntitySnapshot, ...],
    article_text: str,
) -> tuple[str, ...]:
    """Prefer co-mention windows; fall back to per-entity snippets."""
    snippets: list[str] = []
    seen: set[str] = set()
    haystack = article_text or ""

    for left in from_entities:
        for right in to_entities:
            if not left.label or not right.label:
                continue
            left_idx = haystack.find(left.label)
            if left_idx < 0:
                continue
            window_start = max(0, left_idx - 120)
            window_end = min(len(haystack), left_idx + len(left.label) + 180)
            window = haystack[window_start:window_end]
            lower_window = window.lower()
            right_tokens = entity_comention_tokens(
                label=right.label,
                affiliation=right.affiliation,
            )
            if not any(token in lower_window for token in right_tokens):
                continue
            snippet = _trim(window)
            if snippet and snippet not in seen:
                seen.add(snippet)
                snippets.append(snippet)

    if not snippets:
        for entity in (*from_entities, *to_entities):
            for snippet in entity.snippets:
                if snippet not in seen:
                    seen.add(snippet)
                    snippets.append(snippet)

    return tuple(snippets)


def quote_is_supported(
    quote: str,
    *,
    article_text: str,
    from_entity: LinkedEntitySnapshot,
    to_entity: LinkedEntitySnapshot,
    pair_snippets: tuple[str, ...],
) -> bool:
    q = quote.strip()
    if not q:
        return False
    if q in article_text:
        return True
    for snippet in (*pair_snippets, *from_entity.snippets, *to_entity.snippets):
        if q in snippet:
            return True
    return False
