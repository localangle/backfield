"""Signed session tokens (browser cookies)."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

SESSION_MAX_AGE = 7 * 24 * 60 * 60
ORGANIZATION_SELECTION_MAX_AGE = 10 * 60
_ORGANIZATION_SELECTION_SALT = "backfield-organization-selection"


def require_session_secret() -> str:
    """Return the configured session signing secret or raise if unset.

    Resolved at use time (not import time) so tooling that imports this package
    for validation helpers can load without a session secret in the environment.
    """
    secret = (os.getenv("SESSION_SECRET") or os.getenv("SECRET_KEY") or "").strip()
    if not secret:
        raise RuntimeError(
            "SESSION_SECRET must be set to a non-empty value. "
            "Local Compose and tests provide an explicit secret; do not rely on a built-in default."
        )
    return secret


@lru_cache(maxsize=1)
def _session_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(require_session_secret())


def _organization_selection_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        require_session_secret(),
        salt=_ORGANIZATION_SELECTION_SALT,
    )


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
        "token_type": "session",
        "username": email,
        "email": email,
        "user_id": user_id,
        "projects": projects,
        "organization_id": organization_id,
        "org_role": org_role,
        "is_admin": is_admin,
        "exp": int((datetime.now(UTC) + timedelta(days=7)).timestamp()),
    }
    return _session_serializer().dumps(token_data)


def verify_session_token(token: str) -> dict[str, Any] | None:
    """Verify session token and return payload dict if valid."""
    try:
        data = _session_serializer().loads(token, max_age=SESSION_MAX_AGE)
        # Tokens issued before organization switching did not carry a type.
        if data.get("token_type") not in (None, "session"):
            return None
        if "exp" in data:
            exp_timestamp = data["exp"]
            if datetime.now(UTC).timestamp() > exp_timestamp:
                return None
        return data
    except (BadSignature, SignatureExpired):
        return None


def create_organization_selection_token(
    *,
    user_id: int,
    organization_ids: list[int],
) -> str:
    """Create a short-lived token usable only to select one allowed organization."""
    token_data = {
        "token_type": "organization_selection",
        "user_id": user_id,
        "organization_ids": sorted(set(organization_ids)),
        "exp": int(
            (datetime.now(UTC) + timedelta(seconds=ORGANIZATION_SELECTION_MAX_AGE)).timestamp()
        ),
    }
    return _organization_selection_serializer().dumps(token_data)


def verify_organization_selection_token(token: str) -> dict[str, Any] | None:
    """Verify a signed organization-selection token."""
    try:
        data = _organization_selection_serializer().loads(
            token,
            max_age=ORGANIZATION_SELECTION_MAX_AGE,
        )
        if data.get("token_type") != "organization_selection":
            return None
        if datetime.now(UTC).timestamp() > int(data.get("exp", 0)):
            return None
        if not isinstance(data.get("organization_ids"), list):
            return None
        return data
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None
