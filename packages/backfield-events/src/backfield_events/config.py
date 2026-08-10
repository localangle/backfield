"""Feature gate and shared configuration for events and webhooks."""

from __future__ import annotations

import os

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})


def webhooks_enabled() -> bool:
    """Whether event recording and webhook delivery are enabled for this deployment.

    Disabled by default until the production recovery schedule and delivery
    metrics/alerts are deployed (see docs/development/webhooks.md).
    """
    return os.environ.get("BACKFIELD_WEBHOOKS_ENABLED", "").strip().lower() in _TRUE_VALUES


def public_api_base_url() -> str:
    """Optional absolute base for public API links embedded in event payloads."""
    return os.environ.get("BACKFIELD_PUBLIC_API_BASE_URL", "").strip().rstrip("/")


def allow_private_webhook_destinations() -> bool:
    """Local-development escape hatch for SSRF destination checks."""
    raw = os.environ.get("BACKFIELD_WEBHOOK_ALLOW_PRIVATE_DESTINATIONS", "")
    return raw.strip().lower() in _TRUE_VALUES
