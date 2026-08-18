"""Backfield curated AI model template shape shared by APIs and provisioning."""

from __future__ import annotations

from dataclasses import dataclass

AI_CAPABILITY_EMBEDDING = "embedding"
AI_CAPABILITY_JSON = "json"
AI_CAPABILITY_TEXT = "text"
AI_MODEL_KIND_EMBEDDING = "embedding"
AI_MODEL_KIND_GENERATIVE = "generative"


@dataclass(frozen=True)
class CuratedAiModelTemplate:
    """Immutable provider/model metadata for a curated preset."""

    template_id: str
    provider: str
    provider_model_id: str
    label: str
    capabilities: tuple[str, ...]
    model_kind: str = AI_MODEL_KIND_GENERATIVE
