"""Database engine and session factory."""

from __future__ import annotations

import os
from collections.abc import Generator

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

_engine: Engine | None = None


def get_database_url() -> str:
    return os.environ.get(
        "BACKFIELD_DATABASE_URL",
        os.environ.get(
            "DATABASE_URL",
            "postgresql+psycopg://postgres:postgres@localhost:5433/backfield",
        ),
    )


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_database_url(), echo=False)
    return _engine


def get_session_factory():
    def _session():
        return Session(get_engine())

    return _session


def get_session_generator() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request."""
    with Session(get_engine()) as session:
        yield session


def init_db() -> None:
    """Create tables (dev convenience; prefer Alembic in production)."""
    SQLModel.metadata.create_all(get_engine())
