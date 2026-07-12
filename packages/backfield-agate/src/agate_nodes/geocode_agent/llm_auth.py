"""Shared LLM auth checks for GeocodeAgent steps."""

from __future__ import annotations


def has_llm_auth(api_key: str | None, model_config_id: str | None) -> bool:
    """True when a raw provider key or a catalog AI model config id is available."""
    return bool(api_key) or bool((model_config_id or "").strip())
