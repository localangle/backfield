"""Tests for Postgres deadlock detection helper."""

from __future__ import annotations

from backfield_db.deadlock import DEADLOCK_SQLSTATE, is_postgres_deadlock
from sqlalchemy.exc import OperationalError


class _FakeOrig:
    def __init__(self, *, sqlstate: str | None = None, message: str = "") -> None:
        self.sqlstate = sqlstate
        self.pgcode = sqlstate
        self._message = message

    def __str__(self) -> str:
        return self._message


def test_is_postgres_deadlock_by_sqlstate() -> None:
    exc = OperationalError("stmt", {}, _FakeOrig(sqlstate=DEADLOCK_SQLSTATE))
    assert is_postgres_deadlock(exc) is True


def test_is_postgres_deadlock_by_message() -> None:
    exc = OperationalError(
        "stmt",
        {},
        _FakeOrig(message="deadlock detected"),
    )
    assert is_postgres_deadlock(exc) is True


def test_is_postgres_deadlock_false_for_other_errors() -> None:
    exc = OperationalError("stmt", {}, _FakeOrig(sqlstate="23505", message="unique violation"))
    assert is_postgres_deadlock(exc) is False
