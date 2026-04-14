"""Shared authentication for Backfield (session cookies + service Bearer tokens)."""

from backfield_auth.deps import (
    require_auth,
    require_auth_or_service,
    require_project_access,
    require_service_auth,
)
from backfield_auth.service_tokens import SERVICE_TOKENS, verify_service_token
from backfield_auth.session_tokens import create_session_token, verify_session_token

__all__ = [
    "SERVICE_TOKENS",
    "create_session_token",
    "require_auth",
    "require_auth_or_service",
    "require_project_access",
    "require_service_auth",
    "verify_service_token",
    "verify_session_token",
]
