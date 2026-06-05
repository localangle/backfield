"""Shared substrate inputs used across entity-type semantic indexing."""

from backfield_entities.ingest.semantic_indexing.common.article import (
    ArticleSource,
    load_article_source,
)
from backfield_entities.ingest.semantic_indexing.common.context import (
    extract_article_context_snippet,
)

__all__ = ["ArticleSource", "extract_article_context_snippet", "load_article_source"]
