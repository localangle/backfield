"""Fernet helpers for encrypted project secrets."""

from __future__ import annotations

import os

from cryptography.fernet import Fernet, InvalidToken


def fernet_from_env() -> Fernet | None:
    raw = os.environ.get("MASTER_ENCRYPTION_KEY", "").strip()
    if not raw:
        return None
    try:
        return Fernet(raw.encode())
    except Exception:
        return None


def encrypt_secret(plain: str) -> str:
    f = fernet_from_env()
    if f is None:
        raise RuntimeError("MASTER_ENCRYPTION_KEY is not set or invalid")
    return f.encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    f = fernet_from_env()
    if f is None:
        raise RuntimeError("MASTER_ENCRYPTION_KEY is not set or invalid")
    try:
        return f.decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Invalid encrypted secret") from e
