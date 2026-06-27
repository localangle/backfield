"""Shared helpers for SQLite integration tests (no Docker)."""

from __future__ import annotations

import pytest
from sqlalchemy.engine import Engine


def patch_test_engine(monkeypatch: pytest.MonkeyPatch, engine: Engine) -> None:
    """Point shared ``get_engine()`` at a test SQLite engine for /readyz and helpers."""
    monkeypatch.setattr("backfield_db.session.get_engine", lambda: engine)
