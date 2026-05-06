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
    if p == "google":
        # LiteLLM routes Gemini / Gemma API models under the ``gemini/`` prefix and lists prices
        # there (see BerriAI/litellm ``model_prices_and_context_window.json``).
        low = mid.lower()
        if low.startswith("gemini") or low.startswith("gemma"):
            return f"gemini/{mid}"
        return f"google/{mid}"
    if p == "azure":
        return f"azure/{mid}"
    if p == "openrouter":
        return f"openrouter/{mid}"
    return f"{p}/{mid}"


def litellm_model_cost_lookup_keys(provider: str, provider_model_id: str) -> list[str]:
    """Ordered candidate keys for ``litellm.model_cost`` lookups.

    LiteLLM mixes bare IDs (OpenAI-style), ``provider/model`` routes, and provider-specific
    shapes for the same logical endpoint. Try multiple aliases so curated defaults surface pricing
    when available.
    """

    def uniq(keys: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for k in keys:
            k = k.strip()
            if not k or k in seen:
                continue
            seen.add(k)
            out.append(k)
        return out

    p = provider.strip().lower()
    mid = provider_model_id.strip()
    keys: list[str] = []

    keys.append(litellm_model_id(p, mid))
    keys.append(mid)
    keys.append(f"{p}/{mid}")

    if p == "google":
        low = mid.lower()
        if low.startswith("gemini") or low.startswith("gemma"):
            keys.append(f"gemini/{mid}")

    if p == "cohere":
        keys.append(mid.replace("_", "-"))

    if p == "xai" and mid == "grok-4":
        keys.append("openrouter/x-ai/grok-4")

    if p == "mistral":
        if mid == "codestral":
            keys.append("mistral/codestral-latest")
        if mid in {"magistral-medium", "magistral-medium-latest"}:
            keys.append("mistral/magistral-medium-latest")

    if p == "meta-llama":
        if mid == "llama-4-maverick":
            keys.append("groq/meta-llama/llama-4-maverick-17b-128e-instruct")
        if mid == "llama-4-scout":
            keys.append("groq/meta-llama/llama-4-scout-17b-16e-instruct")
        if mid in {"llama-3.3-70b", "llama-3.3-70b-instruct"}:
            keys.append("groq/llama-3.3-70b-versatile")

    if p == "openrouter":
        q_lower = mid.lower()
        if q_lower.startswith("qwen/") and q_lower.endswith("qwq-32b"):
            keys.append("deepinfra/Qwen/QwQ-32B")

    if p == "google" and mid == "gemini-2.5-flash-thinking":
        keys.append("gemini-2.5-flash")
        keys.append("gemini/gemini-2.5-flash")

    return uniq(keys)


def effective_litellm_model_row(
    *,
    litellm_model: str | None,
    provider: str,
    provider_model_id: str,
) -> str:
    """Prefer explicit routing string on the catalog row; else derive from provider + model id."""
    lm = (litellm_model or "").strip()
    if lm:
        return lm
    return litellm_model_id(provider, provider_model_id)
