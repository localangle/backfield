"""Shared pytest configuration for integration tests."""

from __future__ import annotations

import os

# Align with local Compose defaults so session/service helpers match `make smoke` stacks.
os.environ.setdefault("SESSION_SECRET", "dev-session-secret")
os.environ.setdefault("SERVICE_API_TOKEN", "backfield-dev")
# Keep integration tests deterministic when a developer has Redis running locally.
# The dedicated rate-limit tests opt back in with an in-memory fake.
os.environ.setdefault("BACKFIELD_PUBLIC_RATE_LIMIT_ENABLED", "0")
