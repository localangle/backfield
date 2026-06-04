"""Backward-compatible re-exports of substrate source bundles."""

from backfield_stylebook.semantic_indexing.common.article import ArticleSource
from backfield_stylebook.semantic_indexing.location.sources import (
    LocationCanonicalSource,
    LocationEntitySource,
    LocationMentionSource,
    LocationOccurrenceSource,
)
from backfield_stylebook.semantic_indexing.person.sources import (
    PersonCanonicalSource,
    PersonEntitySource,
    PersonMentionSource,
    PersonOccurrenceSource,
)

__all__ = [
    "ArticleSource",
    "LocationCanonicalSource",
    "LocationEntitySource",
    "LocationMentionSource",
    "LocationOccurrenceSource",
    "PersonCanonicalSource",
    "PersonEntitySource",
    "PersonMentionSource",
    "PersonOccurrenceSource",
]
