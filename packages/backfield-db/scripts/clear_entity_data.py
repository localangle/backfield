#!/usr/bin/env python3
"""Truncate substrate, stylebook entity, and Agate run tables (local dev).

Preserves Stylebook catalog shells referenced by backfield_workspace:
  stylebook, stylebook_membership, stylebook_slug_redirect

Preserves Agate graphs and templates (agate_graph, agate_template).

Requires BACKFIELD_CONFIRM_CLEAR=1 (or true/yes) in the environment.
"""

from __future__ import annotations

import os
import sys

from backfield_db.session import get_database_url, get_engine
from sqlalchemy import text
from sqlalchemy.engine import make_url

_CONFIRM_ENV_VALUES = frozenset({"1", "true", "yes"})

# Catalog / access tables — workspaces FK to stylebook.id.
_EXCLUDED_STYLEBOOK_CATALOG_TABLES = frozenset(
    {
        "stylebook",
        "stylebook_membership",
        "stylebook_slug_redirect",
    }
)

_EXCLUDED_AGATE_TABLES = frozenset(
    {
        "agate_graph",
        "agate_template",
    }
)

_DISCOVER_TABLES_SQL = text(
    """
    SELECT tablename
    FROM pg_tables
    WHERE schemaname = 'public'
      AND (
        tablename LIKE 'substrate\\_%' ESCAPE '\\'
        OR tablename LIKE 'stylebook\\_%' ESCAPE '\\'
        OR (
          tablename LIKE 'agate\\_%' ESCAPE '\\'
          AND tablename NOT IN ('agate_graph', 'agate_template')
        )
        OR tablename = 'backfield_ai_call_record'
      )
    ORDER BY tablename
    """
)


def _confirmation_required() -> None:
    if os.environ.get("BACKFIELD_CONFIRM_CLEAR", "").strip().lower() not in _CONFIRM_ENV_VALUES:
        print(
            "Set BACKFIELD_CONFIRM_CLEAR=1 to confirm clearing substrate, "
            "stylebook entity, and Agate run tables.",
            file=sys.stderr,
        )
        sys.exit(1)


def _require_postgres() -> None:
    if make_url(get_database_url()).get_backend_name() != "postgresql":
        print("clear_entity_data only supports PostgreSQL.", file=sys.stderr)
        sys.exit(1)


def discover_entity_tables(connection) -> list[str]:
    rows = connection.execute(_DISCOVER_TABLES_SQL).fetchall()
    tables = [str(row[0]) for row in rows]
    return [
        name
        for name in tables
        if name not in _EXCLUDED_STYLEBOOK_CATALOG_TABLES
        and name not in _EXCLUDED_AGATE_TABLES
    ]


def clear_entity_tables(connection, tables: list[str]) -> None:
    if not tables:
        print("No substrate, stylebook entity, or run tables found.")
        return

    quoted = ", ".join(f'"{name}"' for name in tables)
    connection.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))


def main() -> None:
    _confirmation_required()
    _require_postgres()

    engine = get_engine()
    with engine.begin() as connection:
        tables = discover_entity_tables(connection)
        clear_entity_tables(connection, tables)

    if tables:
        print(f"Cleared {len(tables)} tables:")
        for name in tables:
            print(f"  - {name}")
    print(
        "Preserved: stylebook catalog (stylebook, membership, slug redirects) "
        "and Agate graphs/templates."
    )


if __name__ == "__main__":
    main()
