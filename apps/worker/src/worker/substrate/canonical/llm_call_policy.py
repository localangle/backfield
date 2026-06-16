"""Conservative LLM call defaults for DBOutput persist-time helpers that swallow failures."""

from __future__ import annotations

# Adjudication, name-variant recall, and auto-connection helpers keep the rules-based plan on
# failure, so fast-fail settings remove wasted wall-time without changing linking outcomes.
ADJUDICATION_LLM_MAX_RETRIES = 1
ADJUDICATION_LLM_TIMEOUT_S = 90.0
ADJUDICATION_LLM_SKIP_MAX_TOKENS_BUMP = True
