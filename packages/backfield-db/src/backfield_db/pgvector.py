"""Pgvector column type with SQLite-safe fallback for tests."""

from __future__ import annotations

from sqlalchemy.types import Text, TypeDecorator

DEFAULT_SEMANTIC_EMBEDDING_DIMENSIONS = 1536


class _PostgresVector(TypeDecorator):
    """Render pgvector ``vector(n)`` on Postgres and plain text elsewhere."""

    impl = Text
    cache_ok = True

    def __init__(self, dimensions: int = DEFAULT_SEMANTIC_EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = int(dimensions)
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dimensions))
        return dialect.type_descriptor(Text())
