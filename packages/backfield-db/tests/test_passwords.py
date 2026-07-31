"""Shared password policy boundaries."""

from __future__ import annotations

import pytest
from backfield_db.passwords import validate_password_strength


def test_password_strength_accepts_exact_bcrypt_multibyte_limit() -> None:
    password = "é" * 36
    assert len(password.encode("utf-8")) == 72
    assert validate_password_strength(password) == password


def test_password_strength_rejects_over_bcrypt_multibyte_limit() -> None:
    password = "é" * 37
    assert len(password.encode("utf-8")) == 74
    with pytest.raises(ValueError, match="at most 72 UTF-8 bytes"):
        validate_password_strength(password)
