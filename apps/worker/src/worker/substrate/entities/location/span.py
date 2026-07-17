"""Shared occurrence span matching compatibility wrapper."""

from __future__ import annotations

from backfield_entities.occurrence_spans import find_proven_occurrence_span


def _find_mention_span(
    *, haystack: str, needle: str, search_from: int = 0
) -> tuple[int, int] | None:
    return find_proven_occurrence_span(
        article_text=haystack,
        evidence_texts=(needle,),
        search_from=search_from,
    )
