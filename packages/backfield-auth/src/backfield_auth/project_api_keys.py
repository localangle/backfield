"""
Per-project API keys (future).

Auto-provisioned keys will be stored in backfield-db and verified here. External
scripts and n8n will send `Authorization: Bearer <project_key>`; validation will
map the key to a project id + scopes without treating it as the global service token.
"""

from __future__ import annotations

# Intentionally minimal: project API keys live in `backfield_api_credential` (Core API).

__all__: list[str] = []
