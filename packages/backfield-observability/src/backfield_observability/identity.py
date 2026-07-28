"""Trusted runtime identity for logs and CloudWatch metric dimensions."""

from __future__ import annotations

import os
from dataclasses import dataclass

SERVICE_NAMES = frozenset({"agate-api", "stylebook-api", "core-api", "worker"})


@dataclass(frozen=True)
class RuntimeIdentity:
    """Deployment identity used for structured logs and EMF dimensions."""

    service: str
    environment: str
    version: str
    git_sha: str
    client: str | None


def _env_first(*names: str, default: str | None = None) -> str | None:
    for name in names:
        raw = os.environ.get(name)
        if raw is not None and raw.strip():
            return raw.strip()
    return default


def read_environment() -> str:
    return _env_first("BACKFIELD_ENV", "ENVIRONMENT", default="development") or "development"


def read_runtime_identity(service_name: str) -> RuntimeIdentity:
    """Read service identity from the process environment."""
    return RuntimeIdentity(
        service=service_name,
        environment=read_environment(),
        version=_env_first("APP_VERSION", "BACKFIELD_APP_VERSION", default="0.1.0") or "0.1.0",
        git_sha=_env_first("GIT_SHA", "BACKFIELD_GIT_SHA", default="unknown") or "unknown",
        client=_env_first("BACKFIELD_CLIENT"),
    )


def require_client_for_metrics(identity: RuntimeIdentity) -> str | None:
    """Return the client slug when metrics may be emitted, else None."""
    if identity.client is None:
        return None
    return identity.client
