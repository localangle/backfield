"""Ensure API entrypoints no longer run Alembic on startup."""

from __future__ import annotations

from pathlib import Path


def test_agate_api_entrypoint_does_not_run_alembic() -> None:
    entrypoint = (
        Path(__file__).resolve().parents[1]
        / "apps"
        / "agate-api"
        / "scripts"
        / "entrypoint.sh"
    )
    text = entrypoint.read_text(encoding="utf-8")
    assert "alembic" not in text.lower()
    assert "ensure_database_exists" not in text
    assert "uvicorn" in text
