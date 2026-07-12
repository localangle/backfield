"""null_pool_session must not contend with a held process-pool Session."""

from __future__ import annotations

import os

import pytest
from backfield_db.session import get_engine, null_pool_session
from sqlalchemy import text
from sqlmodel import Session


def test_null_pool_session_works_while_pooled_session_held(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BACKFIELD_SQLALCHEMY_POOL_SIZE", "1")
    monkeypatch.setenv("BACKFIELD_SQLALCHEMY_MAX_OVERFLOW", "0")
    # Force a fresh engine with the size-1 pool for this test process.
    import backfield_db.session as session_mod

    session_mod._engine = None

    url = os.environ.get(
        "BACKFIELD_DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5433/backfield",
    )
    if not url.startswith("postgresql"):
        pytest.skip("postgres-only regression for nested null_pool_session")

    try:
        engine = get_engine()
        with Session(engine) as held:
            held.execute(text("SELECT 1"))
            with null_pool_session() as nested:
                nested.execute(text("SELECT 1"))
    except Exception as exc:
        message = str(exc).lower()
        if "could not connect" in message or "connection refused" in message:
            pytest.skip("postgres not available")
        raise
    finally:
        session_mod._engine = None
