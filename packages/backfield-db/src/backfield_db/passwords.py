"""Password hashing helpers for identity seeding."""

from __future__ import annotations

import bcrypt

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MAX_PASSWORD_UTF8_BYTES = 72
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


def validate_password_strength(password: str, *, email: str | None = None) -> str:
    """Apply the shared Backfield password policy without retaining the plaintext."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters")
    if len(password.encode("utf-8")) > MAX_PASSWORD_UTF8_BYTES:
        raise ValueError(
            f"Password must be at most {MAX_PASSWORD_UTF8_BYTES} UTF-8 bytes"
        )
    lowered = password.lower()
    if lowered in _WEAK_PASSWORDS:
        raise ValueError("Choose a stronger password")
    if email:
        local = email.strip().lower().split("@", 1)[0]
        if local and lowered == local:
            raise ValueError("Password must not match the email local part")
    return password


def hash_password(plain: str) -> str:
    """Hash a password with bcrypt (passlib-compatible $2b$ hashes)."""
    # bcrypt rejects >72-byte secrets; keep the same practical limit for callers.
    password = plain.encode("utf-8")
    return bcrypt.hashpw(password, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash string."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False
