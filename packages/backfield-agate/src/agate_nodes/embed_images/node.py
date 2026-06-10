"""EmbedImages node — vision description + text embedding per image."""

from __future__ import annotations

import os
from typing import Any

from agate_utils.llm import call_llm_with_image
from backfield_ai.embeddings import EmbeddingConfigurationError, embed_texts_for_model_config
from sqlmodel import Session

from agate_nodes.embed_images.images import (
    extract_images,
    find_article_text,
    flatten_input,
    resolve_image_id,
)

DEFAULT_PROMPT = (
    "Describe this image in detail. Use the provided context (caption and article text) "
    "to inform your description, but focus primarily on what you see in the image itself."
)

MAX_ARTICLE_CONTEXT_CHARS = 2000


def _resolve_model_config_id(params: dict[str, Any], *keys: str) -> str:
    for key in keys:
        raw = params.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    raise EmbeddingConfigurationError(
        "Select models from the project catalog on the Embed Images node."
    )


def _resolve_vision_model(params: dict[str, Any], project_id: int) -> tuple[str, str | None]:
    config_id = None
    for key in ("visionAiModelConfigId", "vision_ai_model_config_id"):
        raw = params.get(key)
        if isinstance(raw, str) and raw.strip():
            config_id = raw.strip()
            break

    fallback = str(params.get("visionModel") or params.get("vision_model") or "gpt-4o-mini").strip()
    if not config_id:
        if params.get("visionModel") or params.get("vision_model"):
            return fallback, None
        raise EmbeddingConfigurationError(
            "Embed Images requires a vision model. Choose one in the node settings."
        )

    from backfield_ai.model_resolve import resolve_place_extract_litellm_model
    from backfield_db.session import get_engine

    class _VisionParams:
        model = fallback
        aiModelConfigId = config_id

    with Session(get_engine()) as session:
        resolved = resolve_place_extract_litellm_model(session, project_id, _VisionParams())
    return resolved, config_id


def _build_enhanced_prompt(
    prompt: str,
    *,
    caption: str | None,
    article_text: str | None,
) -> str:
    context_parts: list[str] = []
    if caption:
        context_parts.append(f"Image caption: {caption}")
    if article_text:
        truncated = article_text[:MAX_ARTICLE_CONTEXT_CHARS]
        if len(article_text) > MAX_ARTICLE_CONTEXT_CHARS:
            truncated += "..."
        context_parts.append(f"Article text: {truncated}")
    if not context_parts:
        return prompt
    return prompt + "\n\nContext:\n" + "\n".join(context_parts)


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

    vision_model, vision_config_id = _resolve_vision_model(params, project_id)
    if not vision_model.startswith("gpt"):
        raise EmbeddingConfigurationError(
            f"Image description requires an OpenAI vision model. Got: {vision_model!r}"
        )

    openai_api_key = os.getenv("OPENAI_API_KEY")
    if not openai_api_key:
        raise EmbeddingConfigurationError("OPENAI_API_KEY is required for image description.")

    embedding_config_id = _resolve_model_config_id(
        params,
        "embeddingAiModelConfigId",
        "embedding_ai_model_config_id",
        "aiModelConfigId",
    )

    descriptions: list[str] = []
    prepared: list[dict[str, Any]] = []

    for index, image_obj in enumerate(images):
        if not isinstance(image_obj, dict):
            raise ValueError(f"Image at index {index} is not an object.")
        image_input = image_obj.get("url") or image_obj.get("base64")
        if not isinstance(image_input, str) or not image_input.strip():
            raise ValueError(f"Image at index {index} must have a url or base64 field.")

        caption_raw = image_obj.get("caption") or image_obj.get("alt")
        caption = (
            str(caption_raw).strip()
            if isinstance(caption_raw, str) and caption_raw.strip()
            else None
        )
        enhanced_prompt = _build_enhanced_prompt(
            prompt,
            caption=caption,
            article_text=article_text,
        )

        try:
            generated_text = call_llm_with_image(
                prompt=enhanced_prompt,
                image=image_input,
                model=vision_model,
                force_json=False,
                openai_api_key=openai_api_key,
            )
        except Exception as exc:
            generated_text = f"Error processing image: {exc}"

        result_data = dict(image_obj)
        image_id = resolve_image_id(image_obj)
        result_data["id"] = image_id
        result_data["image_id"] = image_id
        result_data["generated_text"] = generated_text.strip()
        result_data["vision_model"] = vision_model
        if vision_config_id:
            result_data["vision_ai_model_config_id"] = vision_config_id
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
