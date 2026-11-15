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


def test_is_missing_canonical_link_for_canonical_fk_violation() -> None:
    from backfield_db.deadlock import is_missing_canonical_link
    from sqlalchemy.exc import IntegrityError

    message = (
        'insert or update on table "substrate_person" violates foreign key constraint '
        '"substrate_person_stylebook_person_canonical_id_fkey"'
    )
    exc = IntegrityError("stmt", {}, _FakeOrig(sqlstate="23503", message=message))
    assert is_missing_canonical_link(exc) is True


def test_is_missing_canonical_link_false_for_other_foreign_keys_and_errors() -> None:
    from backfield_db.deadlock import is_missing_canonical_link
    from sqlalchemy.exc import IntegrityError

    other_fk = IntegrityError(
        "stmt",
        {},
        _FakeOrig(
            sqlstate="23503",
            message='violates foreign key constraint "substrate_person_project_id_fkey"',
        ),
    )
    other_canonical_column = IntegrityError(
        "stmt",
        {},
        _FakeOrig(
            sqlstate="23503",
            message='violates foreign key constraint "stylebook_alias_canonical_id_fkey"',
        ),
    )
    unique = IntegrityError("stmt", {}, _FakeOrig(sqlstate="23505", message="unique violation"))
    assert is_missing_canonical_link(other_canonical_column) is False
    assert is_missing_canonical_link(other_fk) is False
    assert is_missing_canonical_link(unique) is False
