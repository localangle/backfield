"""Flagship curated catalog heuristics over LiteLLM model_cost."""

from __future__ import annotations

from backfield_ai.curated_catalog import list_curated_templates
from backfield_db.curated_ai_models import AI_MODEL_KIND_EMBEDDING, AI_MODEL_KIND_GENERATIVE

_CHAT = {"mode": "chat"}
_EMBED = {"mode": "embedding"}
_PROVIDER_CAP = 30


def test_flagship_heuristic_includes_current_and_future_ids() -> None:
    catalog = list_curated_templates(
        {
            "gpt-5-nano": _CHAT,
            "gpt-5.4-mini": _CHAT,
            "gpt-6": _CHAT,
            "gpt-4.1": _CHAT,
            "gpt-4.1-mini": _CHAT,
            "gpt-4o": _CHAT,
            "gpt-4": _CHAT,
            "gpt-3.5-turbo": _CHAT,
            "gpt-5-nano-2025-08-07": _CHAT,
            "gpt-4o-audio-preview": _CHAT,
            "gpt-5-codex": _CHAT,
            "text-embedding-3-small": _EMBED,
            "text-embedding-3-large": _EMBED,
            "claude-opus-4-6": _CHAT,
            "claude-sonnet-4": _CHAT,
            "claude-opus-5": _CHAT,
            "claude-3-7-sonnet-20250219": _CHAT,
            "claude-sonnet-4-5-20250929-v1:0": _CHAT,
            "gemini-2.5-pro": _CHAT,
            "gemini-2.5-flash-lite": _CHAT,
            "gemini-3.5-flash": _CHAT,
            "gemini-2.5-flash-image": _CHAT,
            "gemini/gemini-2.5-pro": _CHAT,
            "mistral/mistral-large-latest": _CHAT,
            "mistral/mistral-small-latest": _CHAT,
            "mistral/codestral-latest": _CHAT,
        }
    )
    ids = set(catalog)
    assert "openai:gpt-5-nano" in ids
    assert "openai:gpt-5.4-mini" in ids
    assert "openai:gpt-6" in ids
    assert "openai:gpt-4.1" in ids
    assert "openai:gpt-4.1-mini" in ids
    assert "openai:gpt-4o" not in ids
    assert "openai:gpt-4" not in ids
    assert "openai:gpt-3.5-turbo" not in ids
    assert "openai:gpt-5-nano-2025-08-07" not in ids
    assert "openai:gpt-4o-audio-preview" not in ids
    assert "openai:gpt-5-codex" not in ids
    assert "openai:text-embedding-3-small" in ids
    assert "openai:text-embedding-3-large" in ids
    assert "anthropic:claude-opus-4-6" in ids
    assert "anthropic:claude-sonnet-4" in ids
    assert "anthropic:claude-opus-5" in ids
    assert "anthropic:claude-3-7-sonnet-20250219" not in ids
    assert "gemini:gemini-2.5-pro" in ids
    assert "gemini:gemini-3.5-flash" in ids
    assert "gemini:gemini-2.5-flash-image" not in ids
    assert "mistral:mistral-large-latest" in ids
    assert "mistral:mistral-small-latest" in ids
    assert "mistral:codestral-latest" not in ids
    assert catalog["openai:gpt-5.4-mini"].label == "GPT-5.4 Mini"
    assert catalog["anthropic:claude-opus-4-6"].label == "Claude Opus 4.6"
    assert catalog["gemini:gemini-2.5-flash-lite"].label == "Gemini 2.5 Flash Lite"
    assert catalog["openai:text-embedding-3-small"].model_kind == AI_MODEL_KIND_EMBEDDING
    assert catalog["openai:gpt-6"].model_kind == AI_MODEL_KIND_GENERATIVE


def test_openrouter_keeps_latest_three_per_family() -> None:
    catalog = list_curated_templates(
        {
            "openrouter/qwen/qwen3.6-plus": _CHAT,
            "openrouter/qwen/qwen3.5-397b-a17b": _CHAT,
            "openrouter/qwen/qwen3.5-27b": _CHAT,
            "openrouter/qwen/qwen3.5-122b-a10b": _CHAT,
            "openrouter/qwen/qwen-2.5-coder-32b-instruct": _CHAT,
            "openrouter/qwen/qwen3.5-plus-02-15": _CHAT,
            "openrouter/deepseek/deepseek-v3.2": _CHAT,
            "openrouter/deepseek/deepseek-v3.2-exp": _CHAT,
            "openrouter/deepseek/deepseek-chat-v3.1": _CHAT,
            "openrouter/deepseek/deepseek-r1": _CHAT,
            "openrouter/deepseek/deepseek-r1-0528": _CHAT,
            "openrouter/deepseek/deepseek-chat-v3-0324": _CHAT,
            "openrouter/deepseek/deepseek-chat": _CHAT,
            "together/qwen/qwen3.6-plus": _CHAT,
        }
    )
    qwen = [key for key in catalog if key.startswith("openrouter:qwen-")]
    deepseek = [key for key in catalog if key.startswith("openrouter:deepseek-")]
    assert qwen == [
        "openrouter:qwen-qwen3.6-plus",
        "openrouter:qwen-qwen3.5-397b-a17b",
        "openrouter:qwen-qwen3.5-122b-a10b",
    ]
    assert "openrouter:qwen-qwen-2.5-coder-32b-instruct" not in catalog
    assert "openrouter:qwen-qwen3.5-plus-02-15" not in catalog
    assert len(deepseek) == 3
    assert "openrouter:deepseek-deepseek-v3.2" in catalog
    assert "openrouter:deepseek-deepseek-r1" in catalog
    assert "openrouter:deepseek-deepseek-v3.2-exp" not in catalog
    assert "openrouter:deepseek-deepseek-r1-0528" not in catalog
    assert "openrouter:deepseek-deepseek-chat-v3-0324" not in catalog
    assert catalog["openrouter:qwen-qwen3.6-plus"].provider_model_id == "qwen/qwen3.6-plus"
    assert catalog["openrouter:qwen-qwen3.6-plus"].label == "Qwen3.6 Plus"


def test_presentation_order_is_provider_then_embeddings() -> None:
    catalog = list_curated_templates(
        {
            "mistral/mistral-large-latest": _CHAT,
            "claude-sonnet-4": _CHAT,
            "gemini-2.5-pro": _CHAT,
            "gpt-5-nano": _CHAT,
            "openrouter/qwen/qwen3.6-plus": _CHAT,
            "text-embedding-3-small": _EMBED,
        }
    )
    ids = list(catalog)
    assert ids == [
        "openai:gpt-5-nano",
        "anthropic:claude-sonnet-4",
        "gemini:gemini-2.5-pro",
        "openrouter:qwen-qwen3.6-plus",
        "mistral:mistral-large-latest",
        "openai:text-embedding-3-small",
    ]


def test_heuristic_does_not_silently_truncate_matching_models() -> None:
    cost = {f"gpt-{major}": _CHAT for major in range(5, 40)}
    catalog = list_curated_templates(cost)
    openai_ids = [key for key in catalog if key.startswith("openai:gpt-")]
    assert len(openai_ids) == len(cost)
    assert "openai:gpt-39" in catalog


def test_per_provider_count_stays_under_safety_cap_on_fixture() -> None:
    catalog = list_curated_templates(
        {
            "gpt-5": _CHAT,
            "gpt-5-mini": _CHAT,
            "gpt-5-nano": _CHAT,
            "gpt-4.1": _CHAT,
            "text-embedding-3-small": _EMBED,
            "claude-opus-4-6": _CHAT,
            "claude-sonnet-4-6": _CHAT,
            "gemini-2.5-pro": _CHAT,
            "gemini-2.5-flash": _CHAT,
            "openrouter/qwen/qwen3.6-plus": _CHAT,
            "mistral/mistral-large-latest": _CHAT,
        }
    )
    counts: dict[str, int] = {}
    for template in catalog.values():
        counts[template.provider] = counts.get(template.provider, 0) + 1
    assert all(count <= _PROVIDER_CAP for count in counts.values())
