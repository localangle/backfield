"""OrganizationExtract node for extracting organizations from text using an LLM."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any

from agate_runtime.context import AgateEnvContext
from agate_runtime.upstream_input import flatten_upstream_inputs
from agate_utils.llm import call_llm
from agate_utils.text_chunking import DocumentChunk, envelope_from_payload
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agate_nodes.extraction.chunked_entity_extract import (
    evidence_from_person_or_org,
    extract_entities_over_chunks,
    strip_transient_chunk_keys,
)
from agate_nodes.extraction.grounding import ChunkCandidate
from agate_nodes.extraction.shared_llm import (
    effective_llm_timeout,
    model_config_id_from_params,
    preflight_unchunked_prompt,
    resolve_extract_litellm_model,
)
from agate_nodes.organization_extract.compact_expand import (
    expand_compact_organization_row,
    is_skippable_compact_row_error,
)
from agate_nodes.organization_extract.compact_prompt import COMPACT_OUTPUT_INSTRUCTIONS
from agate_nodes.organization_extract.llm_organization_parse import organization_from_llm_entry
from agate_nodes.organization_extract.organization_schemas import ExtractedOrganization
from agate_nodes.organization_extract.prompt_template import (
    resolve_organization_extract_prompt,
    substitute_prompt_placeholders,
)
from agate_nodes.organization_extract.reconcile import stitch_organization_candidates

logger = logging.getLogger(__name__)


class OrganizationExtractInput(BaseModel):
    model_config = ConfigDict(extra="allow")


class OrganizationExtractParams(BaseModel):
    model: str = Field(default="gpt-4o-mini")
    aiModelConfigId: str | None = Field(default=None)
    prompt_file: str = Field(default="prompts/extract.md")
    prompt: str = Field(default="")
    llmTimeout: int = Field(default=600, ge=60, le=1800)
    output_mode: str = Field(
        default="compact",
        description=(
            "'compact' (LLM emits array rows; Python expands to full dicts) or "
            "'full' (LLM emits full JSON objects)."
        ),
    )

    @field_validator("output_mode", mode="before")
    @classmethod
    def _normalize_output_mode(cls, value: object) -> str:
        mode = str(value or "").strip().lower()
        if mode not in {"full", "compact"}:
            return "compact"
        return mode

    @model_validator(mode="after")
    def _coerce_empty_model_string(self) -> OrganizationExtractParams:
        if not (self.model or "").strip():
            return self.model_copy(update={"model": "gpt-4o-mini"})
        return self


class OrganizationExtractOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str
    organizations: list[dict[str, Any]] = Field(default_factory=list)


class OrganizationExtractNode:
    name = "OrganizationExtract"
    version = "0.1.0"
    category = "extraction"

    Input = OrganizationExtractInput
    Output = OrganizationExtractOutput
    Params = OrganizationExtractParams

    def _extract_json_path(self, input_dict: dict[str, Any], path_spec: str) -> Any:
        if path_spec == "raw":
            return input_dict
        if "," in path_spec:
            fields = [f.strip() for f in path_spec.split(",")]
            base_path = fields[0]
            additional_fields = fields[1:]
            target = self._extract_json_path(input_dict, base_path)
            all_fields = [base_path.split(".")[-1]] + additional_fields

            def pick_fields(obj: Any) -> Any:
                if isinstance(obj, dict):
                    return {f: obj.get(f) for f in all_fields if f in obj}
                return obj

            if isinstance(target, list):
                return [pick_fields(item) for item in target if isinstance(item, dict)]
            return pick_fields(target)

        parts = path_spec.split(".")
        current: dict[str, Any] | list[Any] | Any = input_dict
        for i, part in enumerate(parts):
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list):
                extracted = []
                for item in current:
                    if isinstance(item, dict) and part in item:
                        extracted.append(item[part])
                current = extracted
            else:
                raise ValueError(f"Path '{'.'.join(parts[: i + 1])}' not found in input")
        return current

    def _build_prompt(self, input_dict: dict[str, Any], prompt_template: str) -> str:
        return substitute_prompt_placeholders(
            prompt_template,
            input_dict,
            extract_json_path=self._extract_json_path,
        )

    def _flatten_input(self, input_dict: dict[str, Any]) -> dict[str, Any]:
        return flatten_upstream_inputs(input_dict)

    def _resolve_text(self, input_dict: dict[str, Any], flattened: dict[str, Any]) -> str:
        text = flattened.get("text")
        if not text:
            for node_data in input_dict.values():
                if isinstance(node_data, dict) and "text" in node_data:
                    text = node_data["text"]
                    break
        if not text and isinstance(input_dict.get("text"), str):
            text = input_dict["text"]
        if not text:
            raise ValueError(
                f"No 'text' field found in input state. Available keys: {list(input_dict.keys())}"
            )
        return str(text)

    def _compose_prompt(
        self,
        flattened_input: dict[str, Any],
        params: OrganizationExtractParams,
    ) -> tuple[str, bool]:
        bundled_prompt = self._load_prompt_template(params.prompt_file)
        prompt_template = resolve_organization_extract_prompt(
            bundled=bundled_prompt,
            custom=params.prompt,
        )
        prompt = self._build_prompt(flattened_input, prompt_template)
        use_compact = params.output_mode == "compact"
        if use_compact:
            output_format = self._load_compact_output_format_template()
            output_instructions = COMPACT_OUTPUT_INSTRUCTIONS
        else:
            output_format = self._load_output_format_template()
            output_instructions = (
                "The results should be returned in a JSON that looks like the following."
            )
        return f"{prompt}\n\n{output_instructions}\n\n{output_format}", use_compact

    def _parse_organizations_payload(
        self,
        response_data: Any,
        *,
        use_compact: bool,
    ) -> list[ExtractedOrganization]:
        organizations_data: list[Any]
        if isinstance(response_data, list):
            organizations_data = response_data
        elif isinstance(response_data, dict) and "organizations" in response_data:
            raw_organizations = response_data["organizations"]
            if raw_organizations is None:
                organizations_data = []
            elif isinstance(raw_organizations, list):
                organizations_data = raw_organizations
            else:
                raise ValueError("'organizations' must be an array")
        else:
            raise ValueError(
                "Expected a list of organizations or an object with 'organizations' field"
            )

        organizations: list[ExtractedOrganization] = []
        if not organizations_data:
            return organizations
        parse_errors: list[str] = []
        for raw_entry in organizations_data:
            entry: dict[str, Any]
            if use_compact:
                if isinstance(raw_entry, list) and not raw_entry:
                    logger.warning(
                        "[OrganizationExtract] skipping empty compact organization row"
                    )
                    continue
                if isinstance(raw_entry, list):
                    try:
                        entry = expand_compact_organization_row(raw_entry)
                    except (ValueError, TypeError) as expand_err:
                        msg = str(expand_err)
                        if is_skippable_compact_row_error(msg):
                            logger.warning(
                                "[OrganizationExtract] skipping placeholder compact "
                                "organization row: %s",
                                msg,
                            )
                            continue
                        parse_errors.append(msg)
                        logger.warning(
                            "[OrganizationExtract] skipping invalid compact "
                            "organization row: %s",
                            msg,
                        )
                        continue
                elif isinstance(raw_entry, dict):
                    logger.warning(
                        "[OrganizationExtract] compact mode received object entry; "
                        "using full dict parse fallback"
                    )
                    entry = raw_entry
                else:
                    parse_errors.append("organization entry must be an array or object")
                    continue
            else:
                if not isinstance(raw_entry, dict):
                    parse_errors.append("organization entry must be an object")
                    continue
                entry = raw_entry
            try:
                organizations.append(organization_from_llm_entry(entry))
            except (ValueError, TypeError) as entry_err:
                msg = str(entry_err)
                if is_skippable_compact_row_error(msg):
                    logger.warning(
                        "[OrganizationExtract] skipping placeholder organization entry: %s",
                        msg,
                    )
                    continue
                parse_errors.append(msg)
                logger.warning(
                    "[OrganizationExtract] skipping invalid LLM organization entry: %s",
                    msg,
                )
        if not organizations and parse_errors:
            detail = parse_errors[0] if len(parse_errors) == 1 else "; ".join(parse_errors[:5])
            raise ValueError(
                "Failed to parse LLM response as organizations data: "
                f"no valid organizations. {detail}"
            )
        if not organizations and organizations_data:
            logger.info(
                "[OrganizationExtract] LLM returned no qualifying organizations after "
                "skipping placeholder rows"
            )
        return organizations

    def _parse_chunk_candidates(
        self,
        response_data: Any,
        chunk: DocumentChunk,
        source_text: str,
        *,
        use_compact: bool,
    ) -> list[ChunkCandidate[dict[str, Any]]]:
        organizations = self._parse_organizations_payload(
            response_data, use_compact=use_compact
        )
        raw_organizations: list[Any]
        if isinstance(response_data, list):
            raw_organizations = response_data
        elif isinstance(response_data, dict):
            raw_organizations = response_data.get("organizations") or []
        else:
            raw_organizations = []

        candidates: list[ChunkCandidate[dict[str, Any]]] = []
        for org, raw_entry in zip(organizations, raw_organizations, strict=False):
            payload = org.model_dump()
            if (
                isinstance(raw_entry, list)
                and len(raw_entry) > 5
                and isinstance(raw_entry[5], dict)
            ):
                payload["extras"] = raw_entry[5]
            elif isinstance(raw_entry, dict) and isinstance(raw_entry.get("extras"), dict):
                payload["extras"] = raw_entry["extras"]
            candidates.append(
                evidence_from_person_or_org(
                    payload,
                    source_text=source_text,
                    chunk=chunk,
                )
            )
        return candidates

    def _passthrough_output(
        self,
        *,
        text: str,
        organizations: list[dict[str, Any]],
        flattened_input: dict[str, Any],
        input_dict: dict[str, Any],
        response_data: Any = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> OrganizationExtractOutput:
        output_data: dict[str, Any] = {
            "text": text,
            "organizations": organizations,
        }
        if diagnostics is not None:
            output_data["extraction_diagnostics"] = diagnostics

        llm_top_level_fields: dict[str, Any] = {}
        if isinstance(response_data, dict):
            for key, value in response_data.items():
                if key != "organizations":
                    llm_top_level_fields[key] = value

        for key, value in flattened_input.items():
            if key == "text":
                continue
            if key.startswith("meta_"):
                output_data[key] = value
            elif key not in output_data:
                output_data[key] = value

        for key, value in llm_top_level_fields.items():
            meta_key = f"meta_{key}"
            if meta_key not in flattened_input and key not in output_data:
                output_data[key] = value

        for node_data in input_dict.values():
            if isinstance(node_data, dict):
                for key, value in node_data.items():
                    if key != "text" and key not in output_data:
                        output_data[key] = value
        return OrganizationExtractOutput(**strip_transient_chunk_keys(output_data))

    async def run(
        self,
        inp: OrganizationExtractInput,
        params: OrganizationExtractParams,
        ctx: AgateEnvContext,
    ) -> OrganizationExtractOutput:
        start_time = time.time()
        input_dict = inp.model_dump()
        flattened_input = self._flatten_input(input_dict)
        text = self._resolve_text(input_dict, flattened_input)
        envelope = envelope_from_payload(flattened_input)
        resolved_model = resolve_extract_litellm_model(
            params, log_label="OrganizationExtract"
        )
        system_message = (
            "You are a specialized AI assistant for extracting editorially relevant "
            "organizations from news text. Return only valid JSON."
        )

        if envelope is not None:
            use_compact = params.output_mode == "compact"

            def build_prompt(state: dict[str, Any]) -> str:
                prompt, _ = self._compose_prompt(state, params)
                return prompt

            def parse_chunk(
                response_data: Any,
                chunk: DocumentChunk,
                source_text: str,
            ) -> list[ChunkCandidate[dict[str, Any]]]:
                return self._parse_chunk_candidates(
                    response_data,
                    chunk,
                    source_text,
                    use_compact=use_compact,
                )

            organizations, diagnostics = await extract_entities_over_chunks(
                envelope=envelope,
                flattened=flattened_input,
                params=params,
                ctx=ctx,
                start_time=start_time,
                system_message=system_message,
                log_label="OrganizationExtract",
                build_prompt=build_prompt,
                parse_chunk_response=parse_chunk,
                stitch=stitch_organization_candidates,
                resolved_model=resolved_model,
            )
            return self._passthrough_output(
                text=envelope.text,
                organizations=organizations,
                flattened_input=flattened_input,
                input_dict=input_dict,
                diagnostics=diagnostics,
            )

        prompt, use_compact = self._compose_prompt(flattened_input, params)
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
                f"OrganizationExtract LLM call exceeded timeout of {effective_timeout}s"
            ) from exc

        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            preview = (response_text or "")[:800]
            raise ValueError(
                f"Failed to parse LLM response as organizations data: {e}. Preview: {preview!r}"
            ) from e

        organizations = self._parse_organizations_payload(
            response_data, use_compact=use_compact
        )
        return self._passthrough_output(
            text=text,
            organizations=[org.model_dump() for org in organizations],
            flattened_input=flattened_input,
            input_dict=input_dict,
            response_data=response_data,
        )

    def _load_prompt_template(self, prompt_file_path: str) -> str:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        prompt_file = (
            prompt_file_path
            if os.path.isabs(prompt_file_path)
            else os.path.join(current_dir, prompt_file_path)
        )
        with open(prompt_file, encoding="utf-8") as f:
            return f.read()

    def _load_output_format_template(self) -> str:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, "prompts", "_output_format.json")
        with open(path, encoding="utf-8") as f:
            return f.read()

    def _load_compact_output_format_template(self) -> str:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, "prompts", "_output_format_compact.json")
        with open(path, encoding="utf-8") as f:
            return f.read()
