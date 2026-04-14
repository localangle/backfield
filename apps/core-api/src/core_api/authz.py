"""Re-export DB-backed auth from ``backfield_auth.gate`` for core_api call sites."""

from __future__ import annotations

from backfield_auth.gate import (
    get_auth_dependency,
    require_org_admin,
    require_project_access,
    resolve_auth,
    session_project_ids_for_user,
    try_resolve_bearer_api_key,
    visible_project_ids,
)

__all__ = [
    "get_auth_dependency",
    "require_org_admin",
    "require_project_access",
    "resolve_auth",
    "session_project_ids_for_user",
    "try_resolve_bearer_api_key",
    "visible_project_ids",
]
