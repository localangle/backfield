"""EmbedText node — article-level text embeddings via project AI catalog."""

from __future__ import annotations

import os
from typing import Any

from agate_runtime.upstream_input import flatten_upstream_inputs
from backfield_ai.embeddings import EmbeddingConfigurationError, embed_texts_for_model_config

from agate_nodes.embed_text.composer import compose_article_embed_text


def _flatten_input(input_dict: dict[str, Any]) -> dict[str, Any]:
    return flatten_upstream_inputs(input_dict)


def _resolve_model_config_id(params: dict[str, Any]) -> str:
    for key in ("embedding_ai_model_config_id", "aiModelConfigId", "embeddingAiModelConfigId"):
        raw = params.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    model = params.get("model") or params.get("embedding_model")
    if isinstance(model, str) and model.strip():
        raise EmbeddingConfigurationError(
            "Select an embedding model from the project catalog on the Embed Text node."
        )
    raise EmbeddingConfigurationError(
        "Embed Text requires an embedding model. Choose one in the node settings."
    )


def run_embed_text(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    flattened = _flatten_input(inputs if isinstance(inputs, dict) else {})
    embedded_text = compose_article_embed_text(flattened)

    project_id_raw = os.getenv("BACKFIELD_PROJECT_ID", "").strip()
    if not project_id_raw.isdigit():
        raise RuntimeError(
            "Embed Text requires BACKFIELD_PROJECT_ID (run inside the Agate worker with a project)."
        )
    project_id = int(project_id_raw)
    model_config_id = _resolve_model_config_id(params if isinstance(params, dict) else {})

    batch = embed_texts_for_model_config(
        None,
        project_id=project_id,
        model_config_id=model_config_id,
        texts=[embedded_text],
    )

    if batch.batch_error or not batch.items or batch.items[0].vector is None:
        message = batch.batch_error or (
            batch.items[0].error_message if batch.items else "Embedding failed."
        )
        raise EmbeddingConfigurationError(message or "Embedding failed.")

    vector = list(batch.items[0].vector)
    dimensions = batch.dimensions if batch.dimensions is not None else len(vector)

    return {
        "article_embedding": {
            "embedded_text": embedded_text,
            "embedding": vector,
            "embedding_model": batch.provider_model_id,
            "embedding_dimensions": dimensions,
            "embedding_ai_model_config_id": model_config_id,
        }
    }
