"""
Per-project API keys (future).

Auto-provisioned keys will be stored in backfield-db and verified here. External
scripts and n8n will send `Authorization: Bearer <project_key>`; validation will
map the key to a project id + scopes without treating it as the global service token.
"""

from __future__ import annotations

# Intentionally minimal: implement when `agate_project_api_key` (or similar) exists.

__all__: list[str] = []
