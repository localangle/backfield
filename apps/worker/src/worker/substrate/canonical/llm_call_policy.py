"""Conservative LLM call defaults for DBOutput persist-time helpers that swallow failures."""

from __future__ import annotations

# Adjudication and name-variant recall helpers swallow failures and keep the rules-based
# plan, so fast-fail settings remove wasted wall-time without changing linking outcomes.
# Auto-connections use max_retries/timeout from the db_output wrapper but keep the default
# max_tokens bump so reasoning models can emit JSON after finish_reason=length.
ADJUDICATION_LLM_MAX_RETRIES = 1
ADJUDICATION_LLM_TIMEOUT_S = 90.0
ADJUDICATION_LLM_SKIP_MAX_TOKENS_BUMP = True
