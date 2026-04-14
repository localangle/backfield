"""Signed session tokens (browser cookies), compatible with agate-ai-platform style."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_SECRET = os.getenv("SESSION_SECRET", os.getenv("SECRET_KEY", "dev-secret-key"))
serializer = URLSafeTimedSerializer(SESSION_SECRET)
SESSION_MAX_AGE = 7 * 24 * 60 * 60


def create_session_token(
    username: str,
    user_id: int,
    projects: list[int],
    *,
    is_admin: bool = False,
) -> str:
    """Create a signed session token with embedded project ids (for future RBAC)."""
    token_data: dict[str, Any] = {
        "username": username,
        "user_id": user_id,
        "projects": projects,
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
