"""Shared authentication for Backfield (session cookies + service Bearer tokens)."""

from backfield_auth.deps import (
    require_auth,
    require_auth_or_service,
    require_project_allowlist_dependency,
    require_service_auth,
)
from backfield_auth.gate import (
    get_auth_dependency,
    require_org_admin,
    require_project_access,
    resolve_auth,
    session_project_ids_for_user,
    try_resolve_bearer_api_key,
    visible_project_ids,
)
from backfield_auth.service_tokens import SERVICE_TOKENS, verify_service_token
from backfield_auth.session_tokens import create_session_token, verify_session_token

__all__ = [
    "SERVICE_TOKENS",
    "create_session_token",
    "get_auth_dependency",
    "require_auth",
    "require_auth_or_service",
    "require_org_admin",
    "require_project_access",
    "require_project_allowlist_dependency",
    "require_service_auth",
    "resolve_auth",
    "session_project_ids_for_user",
    "try_resolve_bearer_api_key",
    "verify_service_token",
    "verify_session_token",
    "visible_project_ids",
]
