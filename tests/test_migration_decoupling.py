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


def test_compose_migrate_overrides_agate_api_entrypoint() -> None:
    compose = (
        Path(__file__).resolve().parents[1] / "infra" / "docker-compose.yml"
    ).read_text(encoding="utf-8")
    migrate_block = compose.split("  migrate:", 1)[1].split("\n\n", 1)[0]
    assert 'entrypoint: ["backfield-migrate"]' in migrate_block
    assert "command:" not in migrate_block
