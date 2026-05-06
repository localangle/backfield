"""Build LiteLLM model identifiers from Backfield provider rows."""

from __future__ import annotations


def litellm_model_id(provider: str, provider_model_id: str) -> str:
    p = provider.strip().lower()
    mid = provider_model_id.strip()
    if p == "openai":
        return mid
    if p == "anthropic":
        return f"anthropic/{mid}"
    if p == "gemini":
        return f"gemini/{mid}"
    if p == "azure":
        return f"azure/{mid}"
    if p == "openrouter":
        return f"openrouter/{mid}"
    return f"{p}/{mid}"
