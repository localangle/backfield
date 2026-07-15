"""Signed session tokens (browser cookies)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_MAX_AGE = 7 * 24 * 60 * 60


def require_session_secret() -> str:
    """Return the configured session signing secret or raise if unset."""
    secret = (os.getenv("SESSION_SECRET") or os.getenv("SECRET_KEY") or "").strip()
    if not secret:
        raise RuntimeError(
            "SESSION_SECRET must be set to a non-empty value. "
            "Local Compose and tests provide an explicit secret; do not rely on a built-in default."
        )
    return secret


SESSION_SECRET = require_session_secret()
serializer = URLSafeTimedSerializer(SESSION_SECRET)


def create_session_token(
    *,
    user_id: int,
    email: str,
    projects: list[int],
    organization_id: int,
    org_role: str,
    is_admin: bool = False,
) -> str:
    """Create a signed session token with org scope and project ids."""
    token_data: dict[str, Any] = {
        "username": email,
        "email": email,
        "user_id": user_id,
        "projects": projects,
        "organization_id": organization_id,
        "org_role": org_role,
        "is_admin": is_admin,
        "exp": int((datetime.now(UTC) + timedelta(days=7)).timestamp()),
    }
    return serializer.dumps(token_data)


def verify_session_token(token: str) -> dict[str, Any] | None:
    """Verify session token and return payload dict if valid."""
    try:
        data = serializer.loads(token, max_age=SESSION_MAX_AGE)
        if "exp" in data:
            exp_timestamp = data["exp"]
            if datetime.now(UTC).timestamp() > exp_timestamp:
                return None
        return data
    except (BadSignature, SignatureExpired):
        return None
