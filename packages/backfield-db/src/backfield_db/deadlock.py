"""Postgres deadlock detection for retry wrappers."""

from __future__ import annotations

from sqlalchemy.exc import DBAPIError, OperationalError

DEADLOCK_SQLSTATE = "40P01"


def _orig_indicates_deadlock(orig: object | None) -> bool:
    if orig is None:
        return False
    sqlstate = getattr(orig, "sqlstate", None) or getattr(orig, "pgcode", None)
    if sqlstate == DEADLOCK_SQLSTATE:
        return True
    return "deadlock detected" in str(orig).lower()


def is_postgres_deadlock(exc: BaseException) -> bool:
    """True when ``exc`` (or its DBAPI cause chain) is a Postgres deadlock."""
    if isinstance(exc, (OperationalError, DBAPIError)):
        if _orig_indicates_deadlock(getattr(exc, "orig", None)):
            return True
    if "deadlock detected" in str(exc).lower():
        return True
    cause = getattr(exc, "__cause__", None)
    if cause is not None and cause is not exc and isinstance(cause, BaseException):
        return is_postgres_deadlock(cause)
    return False
