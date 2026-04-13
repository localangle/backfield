"""Execution context: API keys from environment and optional project overlays."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgateEnvContext:
    """
    Drop-in replacement for flowbuilder RunContext.get_api_key behavior.

    Project secrets are applied to os.environ by the worker before graph execution.
    """

    run_id: str = "backfield"
    project_id: int | None = None
    project_system_prompt: str | None = None
    api_keys: dict[str, str] = field(default_factory=dict)
    secrets: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_api_key(self, key_name: str, default: str | None = None) -> str | None:
        if key_name in self.api_keys and self.api_keys[key_name]:
            return self.api_keys[key_name]
        return os.environ.get(key_name, default)

    def get_secret(self, key: str, default: str | None = None) -> str | None:
        if key in self.secrets:
            return self.secrets[key]
        return os.environ.get(key, default)
