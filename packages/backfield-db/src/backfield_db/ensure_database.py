from __future__ import annotations

import os

import psycopg
from psycopg.sql import SQL, Identifier
from sqlalchemy.engine import make_url


def ensure_database_exists() -> None:
    """
    Ensure the target database from DATABASE_URL/BACKFIELD_DATABASE_URL exists.

    This is primarily for local Docker Compose: if the Postgres data directory is
    persisted but the target DB was never created, services that run Alembic on
    startup will fail with "database does not exist".
    """

    raw_url = (
        os.environ.get("BACKFIELD_DATABASE_URL_DIRECT")
        or os.environ.get("BACKFIELD_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
    )
    if not raw_url:
        # Mirror session.py fallback, but don't silently create anything for unknown targets.
        raw_url = "postgresql+psycopg://postgres:postgres@localhost:5433/backfield"

    url = make_url(raw_url)
    target_db = url.database or "backfield"

    host = url.host or "localhost"
    port = url.port or 5432
    user = url.username or "postgres"
    password = url.password or "postgres"

    # Creating a database cannot run inside a transaction.
    with psycopg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        dbname="postgres",
    ) as conn:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
            exists = cur.fetchone() is not None
            if exists:
                return

            cur.execute(SQL("CREATE DATABASE {}").format(Identifier(target_db)))
