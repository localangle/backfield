"""Guard behavior for strict project runtime ownership."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import Connection, create_engine, text


def _migration_module() -> ModuleType:
    path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "070_project_stylebook_runtime.py"
    )
    spec = importlib.util.spec_from_file_location("migration_070", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_schema(conn: Connection) -> None:
    conn.execute(
        text("CREATE TABLE stylebook (id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL)")
    )
    conn.execute(
        text(
            "CREATE TABLE backfield_workspace ("
            "id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL, "
            "stylebook_id INTEGER NOT NULL)"
        )
    )
    conn.execute(
        text(
            "CREATE TABLE backfield_project ("
            "id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL, "
            "workspace_id INTEGER, stylebook_id INTEGER)"
        )
    )


def test_validation_accepts_complete_same_organization_assignments() -> None:
    migration = _migration_module()
    with create_engine("sqlite://").begin() as conn:
        _create_schema(conn)
        conn.execute(text("INSERT INTO stylebook VALUES (10, 1)"))
        conn.execute(text("INSERT INTO backfield_workspace VALUES (20, 1, 10)"))
        conn.execute(text("INSERT INTO backfield_project VALUES (30, 1, 20, 10)"))

        migration._validate_project_ownership(conn)


@pytest.mark.parametrize(
    ("workspace_id", "stylebook_id", "match"),
    [
        (None, 10, "null workspace_id or stylebook_id"),
        (20, None, "null workspace_id or stylebook_id"),
        (20, 11, "missing or cross-organization"),
    ],
)
def test_validation_rejects_invalid_retained_projects(
    workspace_id: int | None,
    stylebook_id: int | None,
    match: str,
) -> None:
    migration = _migration_module()
    with create_engine("sqlite://").begin() as conn:
        _create_schema(conn)
        conn.execute(text("INSERT INTO stylebook VALUES (10, 1), (11, 2)"))
        conn.execute(text("INSERT INTO backfield_workspace VALUES (20, 1, 10)"))
        conn.execute(
            text("INSERT INTO backfield_project VALUES (30, 1, :workspace_id, :stylebook_id)"),
            {"workspace_id": workspace_id, "stylebook_id": stylebook_id},
        )

        with pytest.raises(RuntimeError, match=match):
            migration._validate_project_ownership(conn)


def test_validation_rejects_cross_organization_workspace_catalog() -> None:
    migration = _migration_module()
    with create_engine("sqlite://").begin() as conn:
        _create_schema(conn)
        conn.execute(text("INSERT INTO stylebook VALUES (10, 2)"))
        conn.execute(text("INSERT INTO backfield_workspace VALUES (20, 1, 10)"))

        with pytest.raises(RuntimeError, match="workspace 20"):
            migration._validate_project_ownership(conn)
