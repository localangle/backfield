"""Custom Extract node — LLM extraction of user-defined typed records with mentions."""

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

from agate_nodes.custom_extract.composer import (
    compose_custom_extract_prompt,
    flatten_input,
    resolve_text,
)
from agate_nodes.custom_extract.parse import parse_custom_extract_response
from agate_nodes.custom_extract.schema import CustomFieldSpec, CustomRecordSchema

logger = logging.getLogger(__name__)

TASK_SOFT_TIME_LIMIT = int(os.getenv("TASK_SOFT_TIME_LIMIT", "3600"))
CELERY_TIMEOUT_BUFFER = 300


class CustomExtractInput(BaseModel):
    model_config = ConfigDict(extra="allow")


class CustomExtractParams(BaseModel):
    model: str = Field(default="gpt-4o-mini")
    aiModelConfigId: str | None = Field(default=None)
    record_type: str = Field(default="")
    label: str = Field(default="")
    fields: list[CustomFieldSpec] = Field(default_factory=list)
    instructions: str = Field(default="")
    llmTimeout: int = Field(default=600, ge=60, le=1800)

    @model_validator(mode="after")
    def _coerce_empty_model_string(self) -> CustomExtractParams:
        if not (self.model or "").strip():
            return self.model_copy(update={"model": "gpt-4o-mini"})
        return self

    def record_schema(self) -> CustomRecordSchema:
        return CustomRecordSchema(
            record_type=self.record_type,
            label=self.label,
            fields=self.fields,
        )


class CustomExtractOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str
    custom_records: dict[str, Any]


class CustomExtractNode:
    name = "CustomExtract"
    version = "0.1.0"
    category = "extraction"

    Input = CustomExtractInput
    Output = CustomExtractOutput
    Params = CustomExtractParams

    async def run(
        self,
        inp: CustomExtractInput,
        params: CustomExtractParams,
        ctx: AgateEnvContext,
    ) -> CustomExtractOutput:
        start_time = time.time()
        input_dict = inp.model_dump()
        flattened = flatten_input(input_dict)
        text = resolve_text(flattened)

        record_schema = params.record_schema()
        prompt = compose_custom_extract_prompt(
            record_schema=record_schema,
            instructions=params.instructions,
            text=text,
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
                f"({effective_timeout:.1f}s) for Custom Extract LLM call"
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
                    "[CustomExtract] could not resolve catalog AI model; using legacy id: %s",
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
                        "You are a specialized AI assistant for extracting structured records "
                        "from news text. Return only valid JSON."
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
                f"Custom Extract LLM call exceeded timeout of {effective_timeout}s"
            ) from exc

        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError as exc:
            preview = (response_text or "")[:800]
            raise ValueError(
                f"Failed to parse LLM response as custom records: {exc}. Preview: {preview!r}"
            ) from exc

        result = parse_custom_extract_response(
            response_data,
            record_schema=record_schema,
        )

        output_data: dict[str, Any] = dict(flattened)
        output_data["text"] = text

        # Serial chains of Custom Extract accumulate record types instead of clobbering.
        upstream_records = flattened.get("custom_records")
        merged_records: dict[str, Any] = (
            dict(upstream_records) if isinstance(upstream_records, dict) else {}
        )
        merged_records[record_schema.record_type] = {
            "label": record_schema.label,
            "schema": [spec.model_dump() for spec in record_schema.fields],
            "records": [record.model_dump() for record in result.records],
            "dropped_ungrounded": result.dropped_ungrounded,
        }
        output_data["custom_records"] = merged_records
        return CustomExtractOutput(**output_data)
