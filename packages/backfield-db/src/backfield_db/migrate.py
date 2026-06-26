"""Standalone database migration entrypoint (Alembic upgrade head)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from backfield_db.ensure_database import ensure_database_exists

logger = logging.getLogger(__name__)


def alembic_root() -> Path:
    """Return the backfield-db package root containing alembic.ini."""
    return Path(__file__).resolve().parents[2]


def build_alembic_config() -> Config:
    root = alembic_root()
    ini_path = root / "alembic.ini"
    if not ini_path.is_file():
        raise FileNotFoundError(f"Alembic config not found: {ini_path}")
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("prepend_sys_path", str(root))
    return cfg


def run_migrations() -> None:
    """Ensure the target database exists, then apply Alembic migrations to head."""
    ensure_database_exists()
    command.upgrade(build_alembic_config(), "head")


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
