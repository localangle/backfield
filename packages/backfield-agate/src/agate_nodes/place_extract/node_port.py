"""PlaceExtract node for extracting place information from text using LLM.

Use JSON path placeholders in your prompt to extract specific fields:
  {text} - extracts the text field
  {url} - extracts the url field
  {results.images} - extracts nested results.images object/array
  {results.caption} - extracts only caption field from array elements
  {results.caption, id} - extracts multiple fields from array elements
  {raw} - passes entire input JSON
"""

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
from agate_nodes.place_extract.article_context import extract_article_context
from agate_nodes.place_extract.compact_array_parse import (
    is_compact_array_entry,
    row_to_entry,
)
from agate_nodes.place_extract.compact_expand import expand_compact_entry
from agate_nodes.place_extract.compact_prompt import COMPACT_OUTPUT_INSTRUCTIONS
from agate_nodes.place_extract.llm_location_parse import place_from_llm_location_entry
from agate_nodes.place_extract.place_schemas import Place
from agate_nodes.place_extract.prompt_template import (
    resolve_place_extract_prompt,
    substitute_prompt_placeholders,
)
from agate_nodes.place_extract.reconcile import stitch_place_candidates

logger = logging.getLogger(__name__)


class PlaceExtractInput(BaseModel):
    """Input schema - expects to find text in namespaced state."""

    model_config = ConfigDict(extra="allow")


class PlaceExtractParams(BaseModel):
    """Parameters for PlaceExtract node."""

    model: str = Field(
        default="gpt-4o-mini",
        description="LLM model to use (e.g., gpt-4o-mini, gpt-5, claude-haiku-4-5-20251001)",
    )
    aiModelConfigId: str | None = Field(
        default=None,
        description=(
            "Optional Backfield AI model config id "
            "(overrides model routing when set in worker)"
        ),
    )
    prompt_file: str = Field(
        default="prompts/extract.md",
        description=(
            "Path to the prompt file relative to the node directory. "
            "Defaults to prompts/extract.md"
        ),
    )
    prompt: str = Field(
        default="",
        description=(
            "Optional prompt override saved with the graph. At runtime, the bundled "
            "prompt_file is preferred when this matches the bundled template."
        ),
    )
    llmTimeout: int = Field(
        default=600,
        ge=60,
        le=1800,
        description="Timeout in seconds for the LLM call (default: 10 minutes, max: 30 minutes)",
    )
    output_mode: str = Field(
        default="compact",
        description=(
            "'compact' (LLM emits array rows; Python reconstructs components/mentions) "
            "or 'full' (LLM emits full JSON)."
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
    def _coerce_empty_model_string(self) -> PlaceExtractParams:
        """Saved graphs may persist ``model: \"\"`` which overrides the Field default."""
        if not (self.model or "").strip():
            return self.model_copy(update={"model": "gpt-4o-mini"})
        return self


class PlaceExtractOutput(BaseModel):
    """Output schema - returns extracted places and preserves input state."""

    model_config = ConfigDict(extra="allow")

    text: str = Field(description="Original input text")
    locations: list[Place] = Field(description="List of extracted locations")


class PlaceExtractNode:
    """Node for extracting place information from text using LLM."""

    name = "PlaceExtract"
    version = "0.1.0"
    category = "extraction"

    Input = PlaceExtractInput
    Output = PlaceExtractOutput
    Params = PlaceExtractParams

    def _extract_json_path(self, input_dict: dict[str, Any], path_spec: str) -> Any:
        """
        Extract value from input_dict using JSON path notation (similar to LLMEnrich).
        Supports:
        - Simple path: "text", "url"
        - Nested path: "results.images"
        - Multi-field (comma-separated): "results.caption, id"
        - {raw}: returns full input_dict
        """
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

    def _sanitize_for_prompt(self, value: Any) -> Any:
        """
        Remove geometry data from custom_geographies to avoid huge token costs.
        Preserves essential fields like id, label, type, city, state, etc.
        """
        if isinstance(value, dict):
            if "geocode" in value and isinstance(value["geocode"], dict):
                result = value["geocode"].get("result", {})
                if isinstance(result, dict):
                    sanitized_result = {
                        k: v for k, v in result.items() if k not in ["geometry", "boundaries"]
                    }
                    sanitized_geocode = {**value["geocode"], "result": sanitized_result}
                    return {**value, "geocode": sanitized_geocode}
            return {k: self._sanitize_for_prompt(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._sanitize_for_prompt(item) for item in value]
        return value

    def _extract_for_prompt(self, input_dict: dict[str, Any], path_spec: str) -> Any:
        value = self._extract_json_path(input_dict, path_spec)
        return self._sanitize_for_prompt(value)

    def _build_prompt(self, input_dict: dict[str, Any], prompt_template: str) -> str:
        """Replace {json_path} placeholders when present in input; leave others literal."""
        return substitute_prompt_placeholders(
            prompt_template,
            input_dict,
            extract_json_path=self._extract_for_prompt,
        )

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
            node_keys = [
                list(v.keys()) if isinstance(v, dict) else "not dict"
                for v in input_dict.values()
            ]
            raise ValueError(
                f"No 'text' field found in input state. "
                f"Available keys: {list(input_dict.keys())}, "
                f"Node data keys: {node_keys}"
            )
        return str(text)

    def _compose_prompt(
        self,
        flattened_input: dict[str, Any],
        params: PlaceExtractParams,
    ) -> tuple[str, bool]:
        bundled_prompt = self._load_prompt_template(params.prompt_file)
        prompt_template = resolve_place_extract_prompt(
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

    def _locations_data_from_response(self, response_data: Any) -> list[Any]:
        if isinstance(response_data, list):
            return response_data
        if isinstance(response_data, dict) and "locations" in response_data:
            locations_data = response_data["locations"]
            if locations_data is None:
                return []
            if not isinstance(locations_data, list):
                raise ValueError("Expected a list of locations")
            return locations_data
        raise ValueError("Expected a list of locations or an object with 'locations' field")

    def _evidence_text_for_entry(self, entry: dict[str, Any]) -> str:
        for key in ("evidence_anchor", "original_text"):
            raw = entry.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        mentions = entry.get("mentions") or []
        if isinstance(mentions, list) and mentions:
            first = mentions[0]
            if isinstance(first, dict) and isinstance(first.get("text"), str):
                return first["text"].strip()
        return str(entry.get("location") or "").strip()

    def _parse_locations_payload(
        self,
        response_data: Any,
        *,
        use_compact: bool,
        article_text: str,
    ) -> list[Place]:
        locations_data = self._locations_data_from_response(response_data)
        if not isinstance(locations_data, list):
            raise ValueError("Expected a list of locations")

        parse_errors: list[str] = []
        article_context = extract_article_context(article_text)
        expanded_entries: list[dict[str, Any]] = []
        for raw_entry in locations_data:
            try:
                if use_compact:
                    if isinstance(raw_entry, list):
                        entry = row_to_entry(raw_entry)
                    elif isinstance(raw_entry, dict):
                        entry = raw_entry
                    else:
                        parse_errors.append("location entry must be an object or array")
                        continue
                    if is_compact_array_entry(entry):
                        expanded_entries.append(
                            expand_compact_entry(
                                article_text,
                                entry,
                                context=article_context,
                            )
                        )
                    else:
                        expanded_entries.append(entry)
                else:
                    if not isinstance(raw_entry, dict):
                        parse_errors.append("location entry must be an object")
                        continue
                    expanded_entries.append(raw_entry)
            except (ValueError, TypeError) as entry_err:
                msg = str(entry_err)
                parse_errors.append(msg)
                logger.warning(
                    "[PlaceExtract] skipping invalid LLM location entry: %s",
                    msg,
                )

        locations: list[Place] = []
        for entry in expanded_entries:
            try:
                locations.append(place_from_llm_location_entry(entry))
            except (ValueError, TypeError) as entry_err:
                msg = str(entry_err)
                parse_errors.append(msg)
                logger.warning(
                    "[PlaceExtract] skipping invalid location entry: %s",
                    msg,
                )

        if not locations and locations_data:
            detail = parse_errors[0] if len(parse_errors) == 1 else "; ".join(parse_errors[:5])
            raise ValueError(
                f"Failed to parse LLM response as location data: no valid locations. {detail}"
            )
        return locations

    def _parse_chunk_candidates(
        self,
        response_data: Any,
        chunk: DocumentChunk,
        source_text: str,
        *,
        use_compact: bool,
    ) -> list[ChunkCandidate[dict[str, Any]]]:
        locations_data = self._locations_data_from_response(response_data)
        article_context = extract_article_context(source_text)
        candidates: list[ChunkCandidate[dict[str, Any]]] = []

        for raw_entry in locations_data:
            try:
                if use_compact:
                    if isinstance(raw_entry, list):
                        entry = row_to_entry(raw_entry)
                    elif isinstance(raw_entry, dict):
                        entry = dict(raw_entry)
                    else:
                        continue
                else:
                    if not isinstance(raw_entry, dict):
                        continue
                    entry = dict(raw_entry)

                evidence_text = self._evidence_text_for_entry(entry)
                span = locate_evidence_span(
                    source_text=source_text,
                    chunk=chunk,
                    evidence_text=evidence_text,
                    prefer_owned=True,
                )
                candidate = ChunkCandidate(
                    payload=entry,
                    chunk_index=chunk.index,
                    evidence=span,
                )
                mark_ownership(candidate, chunk=chunk)

                if candidate.owned:
                    if use_compact and is_compact_array_entry(entry):
                        # Reconstruct mentions against the full document after ownership.
                        expanded = expand_compact_entry(
                            source_text,
                            entry,
                            context=article_context,
                        )
                    else:
                        expanded = entry
                    try:
                        place = place_from_llm_location_entry(expanded)
                        candidate.payload = place.model_dump()
                    except (ValueError, TypeError) as entry_err:
                        logger.warning(
                            "[PlaceExtract] skipping invalid owned location entry: %s",
                            entry_err,
                        )
                        continue
                candidates.append(candidate)
            except (ValueError, TypeError) as entry_err:
                logger.warning(
                    "[PlaceExtract] skipping invalid chunk location entry: %s",
                    entry_err,
                )
        return candidates

    def _passthrough_output(
        self,
        *,
        text: str,
        locations: list[dict[str, Any]],
        flattened_input: dict[str, Any],
        input_dict: dict[str, Any],
        response_data: Any = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> PlaceExtractOutput:
        output_data: dict[str, Any] = {
            "text": text,
            "locations": locations,
        }
        if diagnostics is not None:
            output_data["extraction_diagnostics"] = diagnostics

        llm_top_level_fields: dict[str, Any] = {}
        if isinstance(response_data, dict):
            for key, value in response_data.items():
                if key != "locations":
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

        return PlaceExtractOutput(**strip_transient_chunk_keys(output_data))

    async def run(
        self,
        inp: PlaceExtractInput,
        params: PlaceExtractParams,
        ctx: AgateEnvContext,
    ) -> PlaceExtractOutput:
        """Execute place extraction - extract text from namespaced state."""
        start_time = time.time()
        input_dict = inp.model_dump()
        flattened_input = flatten_upstream_inputs(input_dict)

        try:
            meta_keys = [k for k in flattened_input.keys() if k.startswith("meta_")]
            logger.debug("[PlaceExtract] input keys: %s", list(input_dict.keys()))
            logger.debug("[PlaceExtract] flattened keys: %s", list(flattened_input.keys()))
            if meta_keys:
                logger.debug("[PlaceExtract] meta_* keys: %s", meta_keys)
            else:
                logger.debug("[PlaceExtract] no meta_* keys in flattened_input")
        except Exception:
            pass

        text = self._resolve_text(input_dict, flattened_input)
        envelope = envelope_from_payload(flattened_input)
        resolved_model = resolve_extract_litellm_model(params, log_label="PlaceExtract")
        system_message = (
            "You are a specialized AI assistant for extracting editorially relevant, "
            "literal physical place information from news text. Return only valid JSON."
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

            locations, diagnostics = await extract_entities_over_chunks(
                envelope=envelope,
                flattened=flattened_input,
                params=params,
                ctx=ctx,
                start_time=start_time,
                system_message=system_message,
                log_label="PlaceExtract",
                build_prompt=build_prompt,
                parse_chunk_response=parse_chunk,
                stitch=stitch_place_candidates,
                resolved_model=resolved_model,
            )
            return self._passthrough_output(
                text=envelope.text,
                locations=locations,
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

        logger.info(
            "[PlaceExtract] LLM call starting model=%s prompt_chars=%d timeout_s=%.1f "
            "model_config_id=%s project_prompt_overlay=%s output_mode=%s",
            resolved_model,
            len(prompt),
            effective_timeout,
            model_config_id or "none",
            "yes" if ctx.project_system_prompt else "no",
            params.output_mode,
        )

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
            elapsed = time.time() - start_time
            raise TimeoutError(
                f"PlaceExtract LLM call exceeded timeout of {effective_timeout}s "
                f"(elapsed: {elapsed:.1f}s). The text may be too long or the LLM may be slow."
            ) from exc

        elapsed = time.time() - start_time
        logger.info("[PlaceExtract] LLM call finished elapsed_s=%.1f", elapsed)

        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            preview = (response_text or "")[:800]
            raise ValueError(
                f"Failed to parse LLM response as location data: {e}. Preview: {preview!r}"
            ) from e

        try:
            locations = self._parse_locations_payload(
                response_data,
                use_compact=use_compact,
                article_text=text,
            )
        except (ValueError, TypeError) as e:
            raise ValueError(f"Failed to parse LLM response as location data: {e}") from e

        return self._passthrough_output(
            text=text,
            locations=[location.model_dump() for location in locations],
            flattened_input=flattened_input,
            input_dict=input_dict,
            response_data=response_data,
        )

    def _load_prompt_template(self, prompt_file_path: str) -> str:
        """Load the prompt template from the prompts directory."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if os.path.isabs(prompt_file_path):
            prompt_file = prompt_file_path
        else:
            prompt_file = os.path.join(current_dir, prompt_file_path)

        try:
            with open(prompt_file, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Prompt template not found at {prompt_file}") from None
        except Exception as e:
            raise Exception(f"Failed to load prompt template: {e}") from e

    def _load_output_format_template(self) -> str:
        """Load the canonical JSON output example appended to every PlaceExtract prompt."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, "prompts", "_output_format.json")
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Output format template not found at {path}") from None

    def _load_compact_output_format_template(self) -> str:
        """Load the compact array JSON example for compact output mode."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, "prompts", "_output_format_compact.json")
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Compact output format template not found at {path}") from None
