"""Tests for EmbedImages description helpers and model resolution."""

from __future__ import annotations

import pytest
from agate_nodes.embed_images.descriptions import build_description_prompt, image_text_fields
from agate_nodes.embed_images.node import (
    _resolve_description_model,
    _resolve_embedding_model_config_id,
)
from backfield_ai.embeddings import EmbeddingConfigurationError


def test_image_text_fields_reads_caption_alt_and_description() -> None:
    caption, alt, description = image_text_fields(
        {
            "caption": " Hero ",
            "alt": "Hero image",
            "description": "A storefront",
        }
    )
    assert caption == "Hero"
    assert alt == "Hero image"
    assert description == "A storefront"


def test_build_description_prompt_includes_context() -> None:
    prompt = build_description_prompt(
        "Summarize the image.",
        caption="Red barn",
        alt=None,
        description=None,
        article_text="Farm story",
    )
    assert "Summarize the image." in prompt
    assert "Caption: Red barn" in prompt
    assert "Article text: Farm story" in prompt


def test_resolve_description_model_requires_explicit_choice() -> None:
    with pytest.raises(EmbeddingConfigurationError, match="description model"):
        _resolve_description_model({}, project_id=1)


def test_resolve_description_model_honors_legacy_model_string() -> None:
    model, config_id = _resolve_description_model({"visionModel": "gpt-4o"}, project_id=1)
    assert model == "gpt-4o"
    assert config_id is None


def test_resolve_embedding_model_config_id_requires_explicit_or_project_default() -> None:
    with pytest.raises(Exception):
        _resolve_embedding_model_config_id({}, project_id=999_999)
