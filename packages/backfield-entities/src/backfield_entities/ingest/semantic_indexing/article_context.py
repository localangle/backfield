"""Backward-compatible re-exports of article context helpers."""

from backfield_entities.semantic_indexing.common.context import (
    DEFAULT_CONTEXT_CHARS_AFTER,
    DEFAULT_CONTEXT_CHARS_BEFORE,
    extract_article_context_snippet,
)

__all__ = [
    "DEFAULT_CONTEXT_CHARS_AFTER",
    "DEFAULT_CONTEXT_CHARS_BEFORE",
    "extract_article_context_snippet",
]
