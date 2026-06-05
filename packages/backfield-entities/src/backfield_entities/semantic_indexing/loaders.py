"""Backward-compatible re-exports of substrate loaders."""

from backfield_entities.semantic_indexing.common.article import load_article_source
from backfield_entities.semantic_indexing.location.loader import (
    load_sync_bundles as load_location_sync_bundles,
)
from backfield_entities.semantic_indexing.person.loader import (
    load_sync_bundles as load_person_sync_bundles,
)

__all__ = [
    "load_article_source",
    "load_location_sync_bundles",
    "load_person_sync_bundles",
]
