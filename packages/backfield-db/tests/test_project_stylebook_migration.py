"""Backfill behavior for direct project Stylebook ownership."""

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
        / "069_project_stylebook_ownership.py"
    )
    spec = importlib.util.spec_from_file_location("migration_069", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_pre_backfill_schema(conn: Connection) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE backfield_organization (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                slug TEXT NOT NULL
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE stylebook (
                id INTEGER PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                slug TEXT NOT NULL,
                name TEXT NOT NULL,
                is_default BOOLEAN NOT NULL DEFAULT false
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE backfield_workspace (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                stylebook_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                slug TEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (organization_id, slug)
            )
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TABLE backfield_project (
                id INTEGER PRIMARY KEY,
                organization_id INTEGER NOT NULL,
                workspace_id INTEGER,
                stylebook_id INTEGER,
                name TEXT NOT NULL,
                slug TEXT NOT NULL
            )
            """
        )
    )


def test_backfill_copies_workspace_stylebook_and_assigns_orphans() -> None:
    migration = _migration_module()
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        _create_pre_backfill_schema(conn)
        conn.execute(
            text(
                """
                INSERT INTO backfield_organization (id, name, slug)
                VALUES (1, 'One', 'one'), (2, 'Two', 'two')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO stylebook (id, organization_id, slug, name, is_default)
                VALUES
                    (10, 1, 'news', 'News', false),
                    (11, 1, 'default', 'Default', true),
                    (20, 2, 'only', 'Only', false)
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO backfield_workspace
                    (id, organization_id, stylebook_id, name, slug)
                VALUES (100, 1, 10, 'Desk', 'desk')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO backfield_project
                    (id, organization_id, workspace_id, stylebook_id, name, slug)
                VALUES
                    (1000, 1, 100, NULL, 'Assigned', 'assigned'),
                    (2000, 2, NULL, NULL, 'Orphan', 'orphan')
                """
            )
        )

        migration._backfill_project_stylebooks(conn)

        assigned = conn.execute(
            text(
                """
                SELECT workspace_id, stylebook_id
                FROM backfield_project
                WHERE id = 1000
                """
            )
        ).one()
        orphan = conn.execute(
            text(
                """
                SELECT p.workspace_id, p.stylebook_id, w.name, w.slug
                FROM backfield_project AS p
                JOIN backfield_workspace AS w ON w.id = p.workspace_id
                WHERE p.id = 2000
                """
            )
        ).one()

        assert tuple(assigned) == (100, 10)
        assert orphan[0] is not None
        assert tuple(orphan[1:]) == (20, "General", "general")


@pytest.mark.parametrize("failure", ["cross_org", "no_stylebook", "ambiguous_stylebooks"])
def test_backfill_fails_instead_of_guessing(failure: str) -> None:
    migration = _migration_module()
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        _create_pre_backfill_schema(conn)
        conn.execute(
            text(
                """
                INSERT INTO backfield_organization (id, name, slug)
                VALUES (1, 'One', 'one'), (2, 'Two', 'two')
                """
            )
        )
        if failure == "cross_org":
            conn.execute(
                text(
                    """
                    INSERT INTO stylebook (id, organization_id, slug, name, is_default)
                    VALUES (20, 2, 'two', 'Two', true)
                    """
                )
            )
            conn.execute(
                text(
                    """
                    INSERT INTO backfield_workspace
                        (id, organization_id, stylebook_id, name, slug)
                    VALUES (100, 2, 20, 'Foreign', 'foreign')
                    """
                )
            )
            workspace_id = 100
        elif failure == "ambiguous_stylebooks":
            conn.execute(
                text(
                    """
                    INSERT INTO stylebook (id, organization_id, slug, name, is_default)
                    VALUES
                        (10, 1, 'one', 'One', false),
                        (11, 1, 'two', 'Two', false)
                    """
                )
            )
            workspace_id = None
        else:
            workspace_id = None
        conn.execute(
            text(
                """
                INSERT INTO backfield_project
                    (id, organization_id, workspace_id, stylebook_id, name, slug)
                VALUES (1000, 1, :workspace_id, NULL, 'Project', 'project')
                """
            ),
            {"workspace_id": workspace_id},
        )

        with pytest.raises(RuntimeError, match="cross-organization|no Stylebook|no default"):
            migration._backfill_project_stylebooks(conn)
