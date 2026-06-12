"""Article Metadata node — LLM article classification with category, rationale, confidence."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from agate_runtime.context import AgateEnvContext
from agate_utils.llm import call_llm
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agate_nodes.article_metadata.composer import (
    compose_article_metadata_prompt,
    flatten_input,
    load_package_file,
    resolve_text,
)
from agate_nodes.article_metadata.parse import (
    normalize_llm_json_payload,
    parse_article_metadata_response,
    parse_multi_value_metadata_response,
)
from agate_nodes.article_metadata.presets import (
    is_multi_value_preset,
    multi_value_list_key,
    normalize_prompt_preset,
    preset_output_format_relpath,
    preset_prompt_relpath,
    resolve_meta_type,
)

logger = logging.getLogger(__name__)

TASK_SOFT_TIME_LIMIT = int(os.getenv("TASK_SOFT_TIME_LIMIT", "3600"))
CELERY_TIMEOUT_BUFFER = 300


class ArticleMetadataInput(BaseModel):
    model_config = ConfigDict(extra="allow")


class ArticleMetadataParams(BaseModel):
    model: str = Field(default="gpt-4o-mini")
    aiModelConfigId: str | None = Field(default=None)
    prompt_preset: str = Field(default="subject")
    meta_type: str = Field(default="")
    prompt: str = Field(default="")
    llmTimeout: int = Field(default=600, ge=60, le=1800)

    @model_validator(mode="after")
    def _coerce_empty_model_string(self) -> ArticleMetadataParams:
        if not (self.model or "").strip():
            return self.model_copy(update={"model": "gpt-4o-mini"})
        return self


class ArticleMetadataOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str
    article_metadata: dict[str, Any]


class ArticleMetadataNode:
    name = "ArticleMetadata"
    version = "0.1.0"
    category = "enrichment"

    Input = ArticleMetadataInput
    Output = ArticleMetadataOutput
    Params = ArticleMetadataParams

    def _resolve_prompt_template(self, params: ArticleMetadataParams) -> tuple[str, str]:
        preset_id = normalize_prompt_preset(params.prompt_preset)
        custom = params.prompt.strip()
        if preset_id == "custom":
            if not custom:
                raise ValueError("Custom preset requires prompt text on the Prompt tab.")
            return preset_id, custom

        if custom:
            return preset_id, custom

        relpath = preset_prompt_relpath(preset_id)
        if relpath is None:
            raise ValueError(f"No bundled prompt for preset {preset_id!r}.")
        return preset_id, load_package_file(relpath)

    async def run(
        self,
        inp: ArticleMetadataInput,
        params: ArticleMetadataParams,
        ctx: AgateEnvContext,
    ) -> ArticleMetadataOutput:
        start_time = time.time()
        input_dict = inp.model_dump()
        flattened = flatten_input(input_dict)
        text = resolve_text(flattened)

        preset_id, prompt_template = self._resolve_prompt_template(params)
        resolved_meta_type = resolve_meta_type(
            preset_id,
            custom_meta_type=params.meta_type,
        )
        output_format = load_package_file(preset_output_format_relpath(preset_id))
        prompt, allowed_categories = compose_article_metadata_prompt(
            prompt_template=prompt_template,
            flattened=flattened,
            output_format_json=output_format,
            preset_id=preset_id,
        )

        elapsed_time = time.time() - start_time
        max_safe_runtime = TASK_SOFT_TIME_LIMIT - CELERY_TIMEOUT_BUFFER
        if elapsed_time > max_safe_runtime:
            raise TimeoutError(
                f"Node exceeded safe runtime limit ({max_safe_runtime}s) before LLM call"
            )
        remaining_safe_time = max_safe_runtime - elapsed_time
        effective_timeout = min(params.llmTimeout, remaining_safe_time)
        if effective_timeout < 60:
            raise TimeoutError(
                "Insufficient time remaining "
                f"({effective_timeout:.1f}s) for Article Metadata LLM call"
            )

        resolved_model = params.model
        raw_pid = os.getenv("BACKFIELD_PROJECT_ID")
        if raw_pid:
            try:
                from backfield_ai.model_resolve import resolve_place_extract_litellm_model
                from backfield_db.session import get_engine
                from sqlmodel import Session

                with Session(get_engine()) as res_sess:
                    resolved_model = resolve_place_extract_litellm_model(
                        res_sess,
                        int(raw_pid),
                        params,
                    )
            except Exception as exc:
                logger.warning(
                    "[ArticleMetadata] could not resolve catalog AI model; using legacy id: %s",
                    exc,
                )

        raw_mc = getattr(params, "aiModelConfigId", None)
        model_config_id = str(raw_mc).strip() if raw_mc else None

        try:
            response_text = await asyncio.wait_for(
                asyncio.to_thread(
                    call_llm,
                    prompt=prompt,
                    model=resolved_model,
                    system_message=(
                        "You are a specialized AI assistant for classifying news articles. "
                        "Return only valid JSON."
                    ),
                    force_json=True,
                    temperature=0.0,
                    timeout=effective_timeout,
                    openai_api_key=ctx.get_api_key("OPENAI_API_KEY"),
                    anthropic_api_key=ctx.get_api_key("ANTHROPIC_API_KEY"),
                    gemini_api_key=ctx.get_api_key("GEMINI_API_KEY"),
                    openrouter_api_key=ctx.get_api_key("OPENROUTER_API_KEY"),
                    azure_api_key=ctx.get_api_key("AZURE_API_KEY"),
                    azure_api_base=ctx.get_api_key("AZURE_API_BASE"),
                    project_system_prompt=ctx.project_system_prompt,
                    model_config_id=model_config_id,
                ),
                timeout=effective_timeout,
            )
        except TimeoutError as exc:
            raise TimeoutError(
                f"Article Metadata LLM call exceeded timeout of {effective_timeout}s"
            ) from exc

        try:
            response_data = normalize_llm_json_payload(json.loads(response_text))
        except json.JSONDecodeError as exc:
            preview = (response_text or "")[:800]
            raise ValueError(
                f"Failed to parse LLM response as article metadata: {exc}. Preview: {preview!r}"
            ) from exc

        output_data: dict[str, Any] = dict(flattened)
        output_data["text"] = text

        if is_multi_value_preset(preset_id):
            parsed_items = parse_multi_value_metadata_response(
                response_data,
                allowed_categories=allowed_categories,
            )
            primary = parsed_items[0]
            list_key = multi_value_list_key(preset_id)
            items_payload = [
                {
                    "category": item.category,
                    "rationale": item.rationale,
                    "confidence": item.confidence,
                }
                for item in parsed_items
            ]
            output_data["article_metadata"] = {
                "meta_type": resolved_meta_type,
                "category": primary.category,
                "rationale": primary.rationale,
                "confidence": primary.confidence,
                list_key: items_payload,
                "prompt_preset": preset_id,
            }
        else:
            parsed = parse_article_metadata_response(
                response_data,
                allowed_categories=allowed_categories,
            )
            output_data["article_metadata"] = {
                "meta_type": resolved_meta_type,
                "category": parsed.category,
                "rationale": parsed.rationale,
                "confidence": parsed.confidence,
                "prompt_preset": preset_id,
            }

        return ArticleMetadataOutput(**output_data)
