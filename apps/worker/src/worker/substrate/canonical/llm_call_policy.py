"""Conservative LLM call defaults for DBOutput persist-time helpers that swallow failures."""

from __future__ import annotations

# Adjudication, name-variant recall, and auto-connection helpers swallow failures and keep
# the rules-based plan on error. Persist-time calls omit max_tokens so reasoning models
# can finish before emitting JSON. max_retries=1 avoids wasted retries on transient errors.
ADJUDICATION_LLM_MAX_RETRIES = 1
ADJUDICATION_LLM_TIMEOUT_S = 300.0
