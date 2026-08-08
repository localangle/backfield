"""Custom Extract node — LLM extraction of user-defined typed records with mentions."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from agate_runtime.context import AgateEnvContext
from agate_utils.llm import call_llm
from agate_utils.prompt_placeholders import substitute_prompt_placeholders
from agate_utils.text_chunking import DocumentChunk, envelope_from_payload
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agate_nodes.custom_extract.composer import (
    compose_custom_extract_prompt,
    flatten_input,
    resolve_text,
)
from agate_nodes.custom_extract.parse import parse_custom_extract_response
from agate_nodes.custom_extract.reconcile import stitch_custom_candidates
from agate_nodes.custom_extract.schema import CustomFieldSpec, CustomRecordSchema
from agate_nodes.extraction.chunked_entity_extract import (
    extract_entities_over_chunks,
    strip_transient_chunk_keys,
)
from agate_nodes.extraction.grounding import (
    ChunkCandidate,
    locate_evidence_span,
    mark_ownership,
)
from agate_nodes.extraction.shared_llm import (
    effective_llm_timeout,
    model_config_id_from_params,
    preflight_unchunked_prompt,
    resolve_extract_litellm_model,
)

logger = logging.getLogger(__name__)


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

    def _parse_chunk_candidates(
        self,
        response_data: Any,
        chunk: DocumentChunk,
        source_text: str,
        *,
        record_schema: CustomRecordSchema,
    ) -> list[ChunkCandidate[dict[str, Any]]]:
        result = parse_custom_extract_response(
            response_data,
            record_schema=record_schema,
        )
        candidates: list[ChunkCandidate[dict[str, Any]]] = []
        for record in result.records:
            payload = record.model_dump()
            evidence_text = ""
            mentions = payload.get("mentions") or []
            if isinstance(mentions, list) and mentions:
                first = mentions[0]
                if isinstance(first, dict) and isinstance(first.get("text"), str):
                    evidence_text = first["text"].strip()
            if not evidence_text:
                fields = payload.get("fields")
                if isinstance(fields, dict):
                    for value in fields.values():
                        if isinstance(value, str) and value.strip():
                            evidence_text = value.strip()
                            break
            span = locate_evidence_span(
                source_text=source_text,
                chunk=chunk,
                evidence_text=evidence_text,
                prefer_owned=True,
            )
            candidate = ChunkCandidate(
                payload=payload,
                chunk_index=chunk.index,
                evidence=span,
            )
            candidates.append(mark_ownership(candidate, chunk=chunk))
        return candidates

    def _merge_custom_records(
        self,
        *,
        flattened: dict[str, Any],
        record_schema: CustomRecordSchema,
        records: list[dict[str, Any]],
        dropped_ungrounded: int,
    ) -> dict[str, Any]:
        upstream_records = flattened.get("custom_records")
        merged_records: dict[str, Any] = (
            dict(upstream_records) if isinstance(upstream_records, dict) else {}
        )
        merged_records[record_schema.record_type] = {
            "label": record_schema.label,
            "schema": [spec.model_dump() for spec in record_schema.fields],
            "records": records,
            "dropped_ungrounded": dropped_ungrounded,
        }
        return merged_records

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
        envelope = envelope_from_payload(flattened)
        record_schema = params.record_schema()
        resolved_model = resolve_extract_litellm_model(params, log_label="CustomExtract")
        system_message = (
            "You are a specialized AI assistant for extracting structured records "
            "from news text. Return only valid JSON."
        )

        if envelope is not None:

            def build_prompt(state: dict[str, Any]) -> str:
                chunk_text = resolve_text(state)
                instructions = substitute_prompt_placeholders(params.instructions, state)
                return compose_custom_extract_prompt(
                    record_schema=record_schema,
                    instructions=instructions,
                    text=chunk_text,
                )

            def parse_chunk(
                response_data: Any,
                chunk: DocumentChunk,
                source_text: str,
            ) -> list[ChunkCandidate[dict[str, Any]]]:
                return self._parse_chunk_candidates(
                    response_data,
                    chunk,
                    source_text,
                    record_schema=record_schema,
                )

            def stitch(
                candidates: list[ChunkCandidate[dict[str, Any]]],
            ) -> tuple[list[dict[str, Any]], int]:
                # stitch_custom_candidates returns the merged list only.
                return stitch_custom_candidates(
                    candidates,
                    record_type=record_schema.record_type,
                ), 0

            records, diagnostics = await extract_entities_over_chunks(
                envelope=envelope,
                flattened=flattened,
                params=params,
                ctx=ctx,
                start_time=start_time,
                system_message=system_message,
                log_label="CustomExtract",
                build_prompt=build_prompt,
                parse_chunk_response=parse_chunk,
                stitch=stitch,
                resolved_model=resolved_model,
            )
            output_data: dict[str, Any] = dict(flattened)
            output_data["text"] = envelope.text
            output_data["custom_records"] = self._merge_custom_records(
                flattened=flattened,
                record_schema=record_schema,
                records=records,
                dropped_ungrounded=0,
            )
            output_data["extraction_diagnostics"] = diagnostics
            return CustomExtractOutput(**strip_transient_chunk_keys(output_data))

        instructions = substitute_prompt_placeholders(params.instructions, flattened)
        prompt = compose_custom_extract_prompt(
            record_schema=record_schema,
            instructions=instructions,
            text=text,
        )
        effective_timeout = effective_llm_timeout(
            start_time=start_time,
            llm_timeout=params.llmTimeout,
        )
        preflight_unchunked_prompt(
            litellm_model=resolved_model,
            system_message=system_message,
            user_prompt=prompt,
            project_system_prompt=ctx.project_system_prompt,
        )
        model_config_id = model_config_id_from_params(params)

        try:
            response_text = await asyncio.wait_for(
                asyncio.to_thread(
                    call_llm,
                    prompt=prompt,
                    model=resolved_model,
                    system_message=system_message,
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

        output_data = dict(flattened)
        output_data["text"] = text
        output_data["custom_records"] = self._merge_custom_records(
            flattened=flattened,
            record_schema=record_schema,
            records=[record.model_dump() for record in result.records],
            dropped_ungrounded=result.dropped_ungrounded,
        )
        return CustomExtractOutput(**strip_transient_chunk_keys(output_data))
