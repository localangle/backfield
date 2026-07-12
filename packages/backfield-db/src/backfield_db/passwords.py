"""Password hashing helpers for identity seeding."""

from __future__ import annotations

import bcrypt


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
