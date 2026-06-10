"""EmbedImages node — text description + embedding per image (no vision input)."""

from __future__ import annotations

import os
from typing import Any

from agate_utils.llm import call_llm
from backfield_ai.embeddings import EmbeddingConfigurationError, embed_texts_for_model_config
from sqlmodel import Session

from agate_nodes.embed_images.descriptions import (
    DEFAULT_PROMPT,
    build_description_prompt,
    image_text_fields,
)
from agate_nodes.embed_images.images import (
    extract_images,
    find_article_text,
    flatten_input,
    resolve_image_id,
)


def _resolve_description_model(params: dict[str, Any], project_id: int) -> tuple[str, str | None]:
    config_id: str | None = None
    for key in (
        "descriptionAiModelConfigId",
        "description_ai_model_config_id",
        "visionAiModelConfigId",
        "vision_ai_model_config_id",
    ):
        raw = params.get(key)
        if isinstance(raw, str) and raw.strip():
            config_id = raw.strip()
            break

    model_str = ""
    for key in ("descriptionModel", "description_model", "visionModel", "vision_model"):
        raw = params.get(key)
        if isinstance(raw, str) and raw.strip():
            model_str = raw.strip()
            break

    if not config_id:
        if model_str:
            return model_str, None
        raise EmbeddingConfigurationError(
            "Embed Images requires a description model. Choose one in the node settings."
        )

    from backfield_ai.model_resolve import resolve_place_extract_litellm_model
    from backfield_db.session import get_engine

    class _DescriptionParams:
        model = model_str
        aiModelConfigId = config_id

    with Session(get_engine()) as session:
        resolved = resolve_place_extract_litellm_model(session, project_id, _DescriptionParams())
    return resolved, config_id


def _resolve_embedding_model_config_id(params: dict[str, Any], project_id: int) -> str:
    for key in ("embeddingAiModelConfigId", "embedding_ai_model_config_id", "aiModelConfigId"):
        raw = params.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()

    from backfield_ai.model_resolve import resolve_semantic_embedding_model_config_id
    from backfield_db.session import get_engine

    with Session(get_engine()) as session:
        return resolve_semantic_embedding_model_config_id(session, project_id)


def run_embed_images(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    flattened = flatten_input(inputs if isinstance(inputs, dict) else {})
    images = extract_images(flattened)

    prompt = str(params.get("prompt") or DEFAULT_PROMPT).strip() or DEFAULT_PROMPT
    article_text = find_article_text(flattened)

    if not images:
        return {
            "image_embeddings": [],
            "warnings": [
                (
                    "No images found in upstream input. Expected an images array "
                    "or objects with url or base64."
                )
            ],
        }

    project_id_raw = os.getenv("BACKFIELD_PROJECT_ID", "").strip()
    if not project_id_raw.isdigit():
        raise RuntimeError(
            "Embed Images requires BACKFIELD_PROJECT_ID "
            "(run inside the Agate worker with a project)."
        )
    project_id = int(project_id_raw)

    description_model, description_config_id = _resolve_description_model(params, project_id)
    embedding_config_id = _resolve_embedding_model_config_id(params, project_id)

    descriptions: list[str] = []
    prepared: list[dict[str, Any]] = []

    for index, image_obj in enumerate(images):
        if not isinstance(image_obj, dict):
            raise ValueError(f"Image at index {index} is not an object.")
        image_input = image_obj.get("url") or image_obj.get("base64")
        if not isinstance(image_input, str) or not image_input.strip():
            raise ValueError(f"Image at index {index} must have a url or base64 field.")

        caption, alt, existing_description = image_text_fields(image_obj)
        description_prompt = build_description_prompt(
            prompt,
            caption=caption,
            alt=alt,
            description=existing_description,
            article_text=article_text,
        )

        try:
            generated_text = call_llm(
                prompt=description_prompt,
                model=description_model,
                force_json=False,
                model_config_id=description_config_id,
            )
        except Exception as exc:
            generated_text = f"Error generating description: {exc}"

        result_data = dict(image_obj)
        image_id = resolve_image_id(image_obj)
        result_data["id"] = image_id
        result_data["image_id"] = image_id
        result_data["generated_text"] = generated_text.strip()
        result_data["description_model"] = description_model
        if description_config_id:
            result_data["description_ai_model_config_id"] = description_config_id
        prepared.append(result_data)
        descriptions.append(result_data["generated_text"])

    from backfield_db.session import get_engine

    with Session(get_engine()) as session:
        batch = embed_texts_for_model_config(
            session,
            project_id=project_id,
            model_config_id=embedding_config_id,
            texts=descriptions,
        )

    if batch.batch_error:
        raise EmbeddingConfigurationError(batch.batch_error)

    results: list[dict[str, Any]] = []
    for index, item in enumerate(prepared):
        vector_item = batch.items[index] if index < len(batch.items) else None
        if vector_item is None or vector_item.vector is None:
            message = vector_item.error_message if vector_item else "Embedding failed."
            results.append(
                {
                    **item,
                    "embedding": [],
                    "embedding_model": batch.provider_model_id,
                    "embedding_dimensions": 0,
                    "embedding_ai_model_config_id": embedding_config_id,
                    "embedding_error": message or "Embedding failed.",
                }
            )
            continue

        vector = list(vector_item.vector)
        dimensions = batch.dimensions if batch.dimensions is not None else len(vector)
        results.append(
            {
                **item,
                "embedding": vector,
                "embedding_model": batch.provider_model_id,
                "embedding_dimensions": dimensions,
                "embedding_ai_model_config_id": embedding_config_id,
            }
        )

    substrate_images = [
        {
            "id": row.get("id") or row.get("image_id"),
            "url": row.get("url"),
            "caption": row.get("caption"),
        }
        for row in results
        if isinstance(row.get("url"), str) and row["url"].strip()
    ]

    output: dict[str, Any] = {"image_embeddings": results}
    if substrate_images:
        output["images"] = substrate_images
    return output
