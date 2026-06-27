"""Opt-in env-driven first admin user (local/demo/CI only)."""

from __future__ import annotations

import logging
import os
import sys

from backfield_db.session import get_engine
from sqlalchemy.exc import ProgrammingError
from sqlmodel import Session

from core_api.bootstrap_users import BootstrapOrgMissingError, ensure_first_org_admin

logger = logging.getLogger(__name__)

ENV_BOOTSTRAP_FLAG = "BACKFIELD_BOOTSTRAP_ADMIN_FROM_ENV"
ENV_EMAIL = "BACKFIELD_BOOTSTRAP_ADMIN_EMAIL"
ENV_PASSWORD = "BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD"
ENV_PASSWORD_FILE = "BACKFIELD_BOOTSTRAP_ADMIN_PASSWORD_FILE"
ENV_DISPLAY_NAME = "BACKFIELD_BOOTSTRAP_ADMIN_DISPLAY_NAME"
ENV_STRICT = "BACKFIELD_BOOTSTRAP_ADMIN_STRICT"


def _env_truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in ("1", "true", "yes")


def _is_missing_identity_schema_error(exc: Exception) -> bool:
    """True when DB exists but Alembic identity tables (e.g. backfield_user) are not applied yet."""
    orig = getattr(exc, "orig", None)
    if orig is not None and type(orig).__name__ == "UndefinedTable":
        return True
    text = f"{orig or exc}".lower()
    return "does not exist" in text and "backfield_" in text


def resolve_bootstrap_password_from_env() -> str | None:
    path = os.environ.get(ENV_PASSWORD_FILE)
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                return f.read().strip()
        except OSError as e:
            logger.error("Could not read %s: %s", ENV_PASSWORD_FILE, e)
            return None
    pw = os.environ.get(ENV_PASSWORD)
    if pw is None:
        return None
    return pw


def run_env_bootstrap_if_configured() -> None:
    """If BACKFIELD_BOOTSTRAP_ADMIN_FROM_ENV is set, create first admin when DB is empty.

    Misconfiguration (flag on but missing email/password) fails the process when strict
    (default), so local/CI stacks fail fast instead of appearing healthy without an admin.
    """
    if not _env_truthy(os.environ.get(ENV_BOOTSTRAP_FLAG)):
        return

    strict = _env_truthy(os.environ.get(ENV_STRICT, "1"))

    email = (os.environ.get(ENV_EMAIL) or "").strip()
    password = resolve_bootstrap_password_from_env()
    display_raw = os.environ.get(ENV_DISPLAY_NAME)
    display_name = display_raw.strip() if display_raw else None

    if not email or not password:
        logger.error(
            "%s is enabled but %s and a password (%s or %s) are required",
            ENV_BOOTSTRAP_FLAG,
            ENV_EMAIL,
            ENV_PASSWORD,
            ENV_PASSWORD_FILE,
        )
        if strict:
            sys.exit(1)
        return

    with Session(get_engine()) as session:
        try:
            result = ensure_first_org_admin(session, email, password, display_name)
        except BootstrapOrgMissingError as e:
            logger.error("Env bootstrap failed: %s", e)
            if strict:
                sys.exit(1)
            return
        except ProgrammingError as e:
            if _is_missing_identity_schema_error(e):
                logger.warning(
                    "Env bootstrap skipped: identity tables missing; run `backfield migrate` "
                    "(or `make migrate`), then restart core-api."
                )
                return
            raise

    if result is not None:
        logger.info("Env bootstrap: created first org admin (user_id=%s)", result["user_id"])
    else:
        logger.info("Env bootstrap: skipped (users already exist)")
