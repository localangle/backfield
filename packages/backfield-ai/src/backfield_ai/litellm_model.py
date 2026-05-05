"""Build LiteLLM model identifiers from Backfield provider rows."""

from __future__ import annotations


def litellm_model_id(provider: str, provider_model_id: str) -> str:
    p = provider.strip().lower()
    mid = provider_model_id.strip()
    if p == "openai":
        return mid
    if p == "anthropic":
        return f"anthropic/{mid}"
    return f"{p}/{mid}"
