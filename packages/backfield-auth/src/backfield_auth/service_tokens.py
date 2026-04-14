"""Service-to-service Bearer tokens (shared secret, comma-separated in env)."""

from __future__ import annotations

import os

_service_tokens_env = os.getenv("SERVICE_API_TOKENS") or os.getenv("SERVICE_API_TOKEN") or ""
SERVICE_TOKENS: set[str] = {
    t.strip() for t in _service_tokens_env.split(",") if t and t.strip()
}


def verify_service_token(token: str) -> bool:
    return token in SERVICE_TOKENS
