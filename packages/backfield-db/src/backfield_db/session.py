"""Database engine and session factory."""

from __future__ import annotations

import os
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import event, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool
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


def get_database_url_direct() -> str:
    """Direct Postgres URL for migrations/admin (bypasses PgBouncer when set)."""
    direct = os.environ.get("BACKFIELD_DATABASE_URL_DIRECT", "").strip()
    if direct:
        return direct
    return get_database_url()


def _pg_timeout_ms_from_env(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return None
    try:
        return max(0, int(raw.strip()))
    except ValueError:
        return None


def _engine_connect_args(url: str) -> dict[str, Any]:
    connect_args: dict[str, Any] = {}
    try:
        parsed = make_url(url)
        if parsed.get_backend_name() == "sqlite":
            connect_args["check_same_thread"] = False
        elif parsed.get_backend_name() == "postgresql":
            # PgBouncer transaction pooling: disable psycopg3 server-side prepared statements.
            connect_args["prepare_threshold"] = None
    except Exception:
        pass
    return connect_args


def _pool_kwargs_from_env() -> dict[str, int]:
    """Optional pool sizing (per process). See docs/operations/runtime-configuration.md."""
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


def _register_pg_timeout_listeners(engine: Engine) -> None:
    """Apply API-only statement/lock timeouts per transaction (PgBouncer-safe)."""
    stmt_ms = _pg_timeout_ms_from_env("BACKFIELD_PG_STATEMENT_TIMEOUT_MS")
    lock_ms = _pg_timeout_ms_from_env("BACKFIELD_PG_LOCK_TIMEOUT_MS")
    if stmt_ms is None and lock_ms is None:
        return

    @event.listens_for(engine, "after_begin")
    def _set_local_timeouts(session, transaction, connection) -> None:  # noqa: ARG001
        if stmt_ms is not None:
            connection.execute(text(f"SET LOCAL statement_timeout = '{stmt_ms}ms'"))
        if lock_ms is not None:
            connection.execute(text(f"SET LOCAL lock_timeout = '{lock_ms}ms'"))


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
        try:
            if make_url(url).get_backend_name() == "postgresql":
                _register_pg_timeout_listeners(_engine)
        except Exception:
            pass
    return _engine


@contextmanager
def null_pool_session() -> Generator[Session, None, None]:
    """Open a short-lived Session that does not use the process pool.

    Use when a long-held pooled Session (worker ``pool_size=1``) must not block a
    nested progress/status write. Disposes the temporary engine after the block.
    """
    url = get_database_url()
    engine = create_engine(
        url,
        echo=False,
        connect_args=_engine_connect_args(url),
        poolclass=NullPool,
        pool_pre_ping=True,
    )
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


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
