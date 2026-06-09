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


def _find_all_indices(haystack: str, needle: str) -> list[int]:
    if not needle:
        return []
    indices: list[int] = []
    start = 0
    while True:
        idx = haystack.find(needle, start)
        if idx < 0:
            break
        indices.append(idx)
        start = idx + max(1, len(needle))
    return indices


def _comention_tokens_for_entity(entity: LinkedEntitySnapshot) -> tuple[str, ...]:
    return entity_comention_tokens(
        label=entity.label,
        affiliation=entity.affiliation,
        entity_type=entity.entity_type,
    )


def collect_pair_snippets_for_entities(
    *,
    left: LinkedEntitySnapshot,
    right: LinkedEntitySnapshot,
    article_text: str,
) -> tuple[str, ...]:
    """Co-mention windows for one entity pair (all left-label occurrences)."""
    snippets: list[str] = []
    seen: set[str] = set()
    haystack = article_text or ""
    if not left.label or not right.label:
        return ()

    right_tokens = _comention_tokens_for_entity(right)
    for left_idx in _find_all_indices(haystack, left.label):
        window_start = max(0, left_idx - 120)
        window_end = min(len(haystack), left_idx + len(left.label) + 180)
        window = haystack[window_start:window_end]
        lower_window = window.lower()
        if not any(token in lower_window for token in right_tokens):
            continue
        snippet = _trim(window)
        if snippet and snippet not in seen:
            seen.add(snippet)
            snippets.append(snippet)

    return tuple(snippets)


def collect_pair_snippets(
    *,
    from_entities: tuple[LinkedEntitySnapshot, ...],
    to_entities: tuple[LinkedEntitySnapshot, ...],
    article_text: str,
    extra_snippets: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Prefer co-mention windows; fall back to per-entity snippets."""
    snippets: list[str] = []
    seen: set[str] = set()

    for extra in extra_snippets:
        text = extra.strip()
        if text and text not in seen:
            seen.add(text)
            snippets.append(_trim(text))

    for left in from_entities:
        for right in to_entities:
            for snippet in collect_pair_snippets_for_entities(
                left=left,
                right=right,
                article_text=article_text,
            ):
                if snippet not in seen:
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
