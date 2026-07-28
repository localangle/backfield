"""Unit tests for shared identity validation."""

from __future__ import annotations

import pytest
from backfield_auth.identity import (
    CreateUserCredentials,
    validate_email_address,
    validate_password,
)
from pydantic import ValidationError


def test_validate_email_normalizes() -> None:
    assert validate_email_address("  Alice@Example.COM ") == "alice@example.com"


def test_validate_email_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="valid email"):
        validate_email_address("not-an-email")


def test_validate_password_rejects_short_and_weak() -> None:
    with pytest.raises(ValueError, match="at least"):
        validate_password("short")
    with pytest.raises(ValueError, match="stronger"):
        validate_password("password")
    with pytest.raises(ValueError, match="local part"):
        validate_password("alice123", email="alice123@example.com")


def test_create_user_credentials_accepts_org_roles() -> None:
    body = CreateUserCredentials(
        email="user@example.com",
        password="secure-pass-99",
        role="org_admin",
    )
    assert body.email == "user@example.com"
    assert body.role == "org_admin"


def test_create_user_credentials_rejects_bad_role() -> None:
    with pytest.raises(ValidationError):
        CreateUserCredentials(
            email="user@example.com",
            password="secure-pass-99",
            role="superuser",  # type: ignore[arg-type]
        )
