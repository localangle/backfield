"""Re-export DB-backed auth from ``backfield_auth.gate`` for core_api call sites."""

from __future__ import annotations

from backfield_auth.gate import (
    get_auth_dependency,
    require_org_admin,
    require_org_member,
    require_project_access,
    resolve_auth,
    resolve_internal_auth,
    resolve_project_by_slug,
    resolve_public_auth,
    session_project_ids_for_user,
    try_resolve_bearer_api_key,
    visible_project_ids,
)

__all__ = [
    "get_auth_dependency",
    "require_org_admin",
    "require_org_member",
    "require_project_access",
    "resolve_internal_auth",
    "resolve_auth",
    "resolve_project_by_slug",
    "resolve_public_auth",
    "session_project_ids_for_user",
    "try_resolve_bearer_api_key",
    "visible_project_ids",
]
