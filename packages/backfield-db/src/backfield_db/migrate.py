"""Standalone database migration entrypoint (Alembic upgrade head)."""

from __future__ import annotations

import logging
import os
import sys
import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.exc import DBAPIError, OperationalError

from backfield_db.ensure_database import ensure_database_exists

logger = logging.getLogger(__name__)

DEFAULT_MIGRATION_ATTEMPTS = 30
DEFAULT_MIGRATION_RETRY_DELAY_SECONDS = 2.0

_TRANSIENT_DB_ERROR_MARKERS = (
    "connection refused",
    "could not connect",
    "connection timed out",
    "server closed the connection",
    "the database system is starting up",
    "starting up",
    "too many clients",
)


def alembic_root() -> Path:
    """Return the directory containing ``alembic.ini`` and ``alembic/``.

    Resolution order:
    1. ``BACKFIELD_ALEMBIC_ROOT`` when set (prod images copy Alembic assets there)
    2. Editable / source-tree layout: ``packages/backfield-db`` (``migrate.py`` → parents[2])
    """
    override = (os.environ.get("BACKFIELD_ALEMBIC_ROOT") or "").strip()
    if override:
        root = Path(override).expanduser().resolve()
        if not (root / "alembic.ini").is_file():
            raise FileNotFoundError(
                f"BACKFIELD_ALEMBIC_ROOT={root} does not contain alembic.ini"
            )
        return root

    # Editable install / repo checkout: .../packages/backfield-db/src/backfield_db/migrate.py
    candidate = Path(__file__).resolve().parents[2]
    if (candidate / "alembic.ini").is_file():
        return candidate

    raise FileNotFoundError(
        "Alembic config not found. Set BACKFIELD_ALEMBIC_ROOT to the directory "
        "containing alembic.ini, or install backfield-db in editable mode from "
        "packages/backfield-db."
    )


def build_alembic_config() -> Config:
    root = alembic_root()
    ini_path = root / "alembic.ini"
    if not ini_path.is_file():
        raise FileNotFoundError(f"Alembic config not found: {ini_path}")
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(root))
    return cfg


def is_transient_db_error(exc: BaseException) -> bool:
    """Return True when a migration failure may clear after Postgres finishes starting."""
    if isinstance(exc, (OperationalError, DBAPIError)):
        return True

    try:
        import psycopg
    except ImportError:
        psycopg = None

    if psycopg is not None and isinstance(exc, psycopg.OperationalError):
        return True

    message = str(exc).lower()
    return any(marker in message for marker in _TRANSIENT_DB_ERROR_MARKERS)


def run_migrations(
    *,
    max_attempts: int = DEFAULT_MIGRATION_ATTEMPTS,
    retry_delay_seconds: float = DEFAULT_MIGRATION_RETRY_DELAY_SECONDS,
) -> None:
    """Ensure the target database exists, then apply Alembic migrations to head."""
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            ensure_database_exists()
            command.upgrade(build_alembic_config(), "head")
            return
        except Exception as exc:
            last_error = exc
            if not is_transient_db_error(exc) or attempt >= max_attempts:
                raise
            logger.warning(
                "Database not ready for migrations (attempt %s/%s): %s",
                attempt,
                max_attempts,
                exc,
            )
            time.sleep(retry_delay_seconds)

    if last_error is not None:
        raise last_error


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        run_migrations()
    except Exception as exc:
        logger.error("Migration failed: %s", exc)
        return 1
    logger.info("Migrations applied successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
