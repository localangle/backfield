"""Shared identity validation for emails, passwords, and organization roles."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

OrgRole = Literal["member", "org_admin"]

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MAX_EMAIL_LENGTH = 320
MAX_DISPLAY_NAME_LENGTH = 200

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_WEAK_PASSWORDS = frozenset(
    {
        "admin",
        "password",
        "password1",
        "password123",
        "12345678",
        "qwertyui",
        "letmein1",
        "changeme",
        "backfield",
    }
)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email_address(email: str) -> str:
    normalized = normalize_email(email)
    if not normalized or len(normalized) > MAX_EMAIL_LENGTH or _EMAIL_RE.match(normalized) is None:
        raise ValueError("Enter a valid email address")
    return normalized


def validate_password(password: str, *, email: str | None = None) -> str:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")
    lowered = password.lower()
    if lowered in _WEAK_PASSWORDS:
        raise ValueError("Choose a stronger password")
    if email:
        local = normalize_email(email).split("@", 1)[0]
        if local and lowered == local:
            raise ValueError("Password must not match the email local part")
    return password


class LoginCredentials(BaseModel):
    email: str = Field(min_length=1, max_length=MAX_EMAIL_LENGTH)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return validate_email_address(value)


class NewPasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    new_password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)

    def validated_new_password(self, *, email: str) -> str:
        return validate_password(self.new_password, email=email)


class CreateUserCredentials(BaseModel):
    email: str = Field(min_length=1, max_length=MAX_EMAIL_LENGTH)
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)
    display_name: str | None = Field(default=None, max_length=MAX_DISPLAY_NAME_LENGTH)
    role: OrgRole = "member"

    @field_validator("email")
    @classmethod
    def _email(cls, value: str) -> str:
        return validate_email_address(value)

    @field_validator("password")
    @classmethod
    def _password(cls, value: str, info) -> str:
        email = info.data.get("email")
        return validate_password(value, email=email if isinstance(email, str) else None)

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
