"""Database engine and session factory."""

from __future__ import annotations

import os
from collections.abc import Generator
from typing import Any

from sqlalchemy.engine import Engine, make_url
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


def _pg_timeout_options_from_env() -> str | None:
    """Optional Postgres session timeouts (API services only; worker leaves unset)."""
    parts: list[str] = []
    raw_stmt = os.environ.get("BACKFIELD_PG_STATEMENT_TIMEOUT_MS")
    if raw_stmt is not None and raw_stmt.strip() != "":
        try:
            ms = max(0, int(raw_stmt.strip()))
            parts.append(f"-c statement_timeout={ms}")
        except ValueError:
            pass
    raw_lock = os.environ.get("BACKFIELD_PG_LOCK_TIMEOUT_MS")
    if raw_lock is not None and raw_lock.strip() != "":
        try:
            ms = max(0, int(raw_lock.strip()))
            parts.append(f"-c lock_timeout={ms}")
        except ValueError:
            pass
    if not parts:
        return None
    return " ".join(parts)


def _engine_connect_args(url: str) -> dict[str, Any]:
    connect_args: dict[str, Any] = {}
    try:
        parsed = make_url(url)
        if parsed.get_backend_name() == "sqlite":
            connect_args["check_same_thread"] = False
        elif parsed.get_backend_name() == "postgresql":
            pg_options = _pg_timeout_options_from_env()
            if pg_options:
                connect_args["options"] = pg_options
    except Exception:
        pass
    return connect_args


def _pool_kwargs_from_env() -> dict[str, int]:
    """Optional pool sizing (per process). See docs/OPERATIONS.md."""
    out: dict[str, int] = {}
    raw_ps = os.environ.get("BACKFIELD_SQLALCHEMY_POOL_SIZE")
    raw_mo = os.environ.get("BACKFIELD_SQLALCHEMY_MAX_OVERFLOW")
    if raw_ps is not None and raw_ps.strip() != "":
        try:
            out["pool_size"] = max(1, int(raw_ps.strip()))
        except ValueError:
            pass
    if raw_mo is not None and raw_mo.strip() != "":
        try:
            out["max_overflow"] = max(0, int(raw_mo.strip()))
        except ValueError:
            pass
    return out


def get_engine() -> Engine:
    """Process-wide SQLAlchemy engine (one pool per interpreter).

    Callers should use ``Session(get_engine())`` (or ``get_session_generator``) instead of
    creating ad-hoc ``create_engine`` instances — extra engines multiply pools and can exhaust
    Postgres ``max_connections`` under Celery concurrency.
    """
    global _engine
    if _engine is None:
        url = get_database_url()
        _engine = create_engine(
            url,
            echo=False,
            connect_args=_engine_connect_args(url),
            pool_pre_ping=True,
            **_pool_kwargs_from_env(),
        )
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
