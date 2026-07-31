"""Backfield-owned curated AI model templates shared by APIs and provisioning."""

from __future__ import annotations

from dataclasses import dataclass

AI_CAPABILITY_EMBEDDING = "embedding"
AI_CAPABILITY_JSON = "json"
AI_CAPABILITY_TEXT = "text"
AI_MODEL_KIND_EMBEDDING = "embedding"
AI_MODEL_KIND_GENERATIVE = "generative"


@dataclass(frozen=True)
class CuratedAiModelTemplate:
    """Immutable provider/model metadata shipped with Backfield."""

    template_id: str
    provider: str
    provider_model_id: str
    label: str
    capabilities: tuple[str, ...]
    model_kind: str = AI_MODEL_KIND_GENERATIVE


def _generative(
    template_id: str,
    provider: str,
    provider_model_id: str,
    label: str,
) -> CuratedAiModelTemplate:
    return CuratedAiModelTemplate(
        template_id=template_id,
        provider=provider,
        provider_model_id=provider_model_id,
        label=label,
        capabilities=(AI_CAPABILITY_TEXT, AI_CAPABILITY_JSON),
    )


_GENERATIVE_TEMPLATE_ROWS: tuple[tuple[str, str, str, str], ...] = (
    ("openai:gpt-5.6", "openai", "gpt-5.6", "GPT-5.6"),
    ("openai:gpt-5.6-sol", "openai", "gpt-5.6-sol", "GPT-5.6 Sol"),
    ("openai:gpt-5.6-terra", "openai", "gpt-5.6-terra", "GPT-5.6 Terra"),
    ("openai:gpt-5.6-luna", "openai", "gpt-5.6-luna", "GPT-5.6 Luna"),
    ("openai:gpt-5.5", "openai", "gpt-5.5", "GPT-5.5"),
    ("openai:gpt-5.4", "openai", "gpt-5.4", "GPT-5.4"),
    ("openai:gpt-5.4-mini", "openai", "gpt-5.4-mini", "GPT-5.4 Mini"),
    ("openai:gpt-5.4-nano", "openai", "gpt-5.4-nano", "GPT-5.4 Nano"),
    ("openai:gpt-5", "openai", "gpt-5", "GPT-5"),
    ("openai:gpt-5-mini", "openai", "gpt-5-mini", "GPT-5 Mini"),
    ("openai:gpt-5-nano", "openai", "gpt-5-nano", "GPT-5 Nano"),
    ("openai:gpt-4.1", "openai", "gpt-4.1", "GPT-4.1"),
    ("openai:gpt-4.1-mini", "openai", "gpt-4.1-mini", "GPT-4.1 Mini"),
    (
        "anthropic:claude-opus-4-6",
        "anthropic",
        "claude-opus-4-6",
        "Claude Opus 4.6",
    ),
    (
        "anthropic:claude-sonnet-4-6",
        "anthropic",
        "claude-sonnet-4-6",
        "Claude Sonnet 4.6",
    ),
    (
        "anthropic:claude-opus-4-5",
        "anthropic",
        "claude-opus-4-5",
        "Claude Opus 4.5",
    ),
    (
        "anthropic:claude-sonnet-4-5",
        "anthropic",
        "claude-sonnet-4-5",
        "Claude Sonnet 4.5",
    ),
    (
        "anthropic:claude-opus-4-1",
        "anthropic",
        "claude-opus-4-1",
        "Claude Opus 4.1",
    ),
    (
        "anthropic:claude-sonnet-4",
        "anthropic",
        "claude-sonnet-4",
        "Claude Sonnet 4",
    ),
    (
        "anthropic:claude-3-7-sonnet-20250219",
        "anthropic",
        "claude-3-7-sonnet-20250219",
        "Claude 3.7 Sonnet",
    ),
    ("gemini:gemini-2.5-pro", "gemini", "gemini-2.5-pro", "Gemini 2.5 Pro"),
    (
        "gemini:gemini-2.5-flash",
        "gemini",
        "gemini-2.5-flash",
        "Gemini 2.5 Flash",
    ),
    (
        "gemini:gemini-2.5-flash-lite",
        "gemini",
        "gemini-2.5-flash-lite",
        "Gemini 2.5 Flash Lite",
    ),
    (
        "gemini:gemini-2.0-flash",
        "gemini",
        "gemini-2.0-flash",
        "Gemini 2.0 Flash",
    ),
    (
        "openrouter:qwen-qwen3.6-plus",
        "openrouter",
        "qwen/qwen3.6-plus",
        "Qwen3.6 Plus",
    ),
    (
        "openrouter:qwen-qwen3.6-35b-a3b",
        "openrouter",
        "qwen/qwen3.6-35b-a3b",
        "Qwen3.6 35B A3B",
    ),
    (
        "openrouter:qwen-qwen3-235b-a22b-2507",
        "openrouter",
        "qwen/qwen3-235b-a22b-2507",
        "Qwen3 235B A22B",
    ),
    (
        "openrouter:deepseek-deepseek-r1",
        "openrouter",
        "deepseek/deepseek-r1",
        "DeepSeek R1",
    ),
    (
        "openrouter:deepseek-deepseek-v3.2",
        "openrouter",
        "deepseek/deepseek-v3.2",
        "DeepSeek V3.2",
    ),
    (
        "mistral:mistral-large-latest",
        "mistral",
        "mistral-large-latest",
        "Mistral Large",
    ),
)


# Insertion order is part of the curated-options presentation contract.
CURATED_TEMPLATES: dict[str, CuratedAiModelTemplate] = {
    template_id: _generative(template_id, provider, provider_model_id, label)
    for template_id, provider, provider_model_id, label in _GENERATIVE_TEMPLATE_ROWS
}
CURATED_TEMPLATES.update(
    {
        "openai:text-embedding-3-small": CuratedAiModelTemplate(
            template_id="openai:text-embedding-3-small",
            provider="openai",
            provider_model_id="text-embedding-3-small",
            label="text-embedding-3-small",
            capabilities=(AI_CAPABILITY_EMBEDDING,),
            model_kind=AI_MODEL_KIND_EMBEDDING,
        ),
        "openai:text-embedding-3-large": CuratedAiModelTemplate(
            template_id="openai:text-embedding-3-large",
            provider="openai",
            provider_model_id="text-embedding-3-large",
            label="text-embedding-3-large",
            capabilities=(AI_CAPABILITY_EMBEDDING,),
            model_kind=AI_MODEL_KIND_EMBEDDING,
        ),
    }
)
