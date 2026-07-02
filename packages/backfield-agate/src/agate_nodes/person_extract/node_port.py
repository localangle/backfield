"""PersonExtract node for extracting people from text using an LLM."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any

from agate_runtime.context import AgateEnvContext
from agate_runtime.upstream_input import flatten_upstream_inputs
from agate_utils.llm import call_llm
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agate_nodes.person_extract.compact_expand import (
    expand_compact_person_row,
    is_skippable_compact_row_error,
)
from agate_nodes.person_extract.compact_prompt import COMPACT_OUTPUT_INSTRUCTIONS
from agate_nodes.person_extract.llm_person_parse import person_from_llm_entry
from agate_nodes.person_extract.person_schemas import ExtractedPerson

logger = logging.getLogger(__name__)

TASK_SOFT_TIME_LIMIT = int(os.getenv("TASK_SOFT_TIME_LIMIT", "3600"))
CELERY_TIMEOUT_BUFFER = 300


class PersonExtractInput(BaseModel):
    model_config = ConfigDict(extra="allow")


class PersonExtractParams(BaseModel):
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
    def _coerce_empty_model_string(self) -> PersonExtractParams:
        if not (self.model or "").strip():
            return self.model_copy(update={"model": "gpt-4o-mini"})
        return self


class PersonExtractOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    text: str
    people: list[dict[str, Any]] = Field(default_factory=list)


class PersonExtractNode:
    name = "PersonExtract"
    version = "0.1.0"
    category = "extraction"

    Input = PersonExtractInput
    Output = PersonExtractOutput
    Params = PersonExtractParams

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
        esc_open = "___ESCAPED_OPEN_BRACE___"
        esc_close = "___ESCAPED_CLOSE_BRACE___"
        temp_template = prompt_template.replace("{{", esc_open).replace("}}", esc_close)
        placeholders = re.findall(r"\{([^}]+)\}", temp_template)
        prompt = temp_template
        for placeholder in placeholders:
            placeholder_key = placeholder.strip()
            value = self._extract_json_path(input_dict, placeholder_key)
            if isinstance(value, (dict, list)):
                serialized = json.dumps(value, indent=2)
            elif isinstance(value, str):
                serialized = value
            else:
                serialized = json.dumps(value)
            prompt = prompt.replace(f"{{{placeholder}}}", serialized)
        return prompt.replace(esc_open, "{{").replace(esc_close, "}}")

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

    async def run(
        self,
        inp: PersonExtractInput,
        params: PersonExtractParams,
        ctx: AgateEnvContext,
    ) -> PersonExtractOutput:
        start_time = time.time()
        input_dict = inp.model_dump()
        flattened_input = self._flatten_input(input_dict)
        text = self._resolve_text(input_dict, flattened_input)

        prompt_template = (
            params.prompt.strip()
            if params.prompt and params.prompt.strip()
            else self._load_prompt_template(params.prompt_file)
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
        prompt = f"{prompt}\n\n{output_instructions}\n\n{output_format}"

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
                f"Insufficient time remaining ({effective_timeout:.1f}s) for PersonExtract LLM call"
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
                    "[PersonExtract] could not resolve catalog AI model; using legacy id: %s",
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
                        "You are a specialized AI assistant for extracting editorially relevant "
                        "people from news text. Return only valid JSON."
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
                f"PersonExtract LLM call exceeded timeout of {effective_timeout}s"
            ) from exc

        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError as e:
            preview = (response_text or "")[:800]
            raise ValueError(
                f"Failed to parse LLM response as people data: {e}. Preview: {preview!r}"
            ) from e

        people_data: list[Any]
        if isinstance(response_data, list):
            people_data = response_data
        elif isinstance(response_data, dict) and "people" in response_data:
            raw_people = response_data["people"]
            if raw_people is None:
                people_data = []
            elif isinstance(raw_people, list):
                people_data = raw_people
            else:
                raise ValueError("'people' must be an array")
        else:
            raise ValueError("Expected a list of people or an object with 'people' field")

        people: list[ExtractedPerson] = []
        if people_data:
            parse_errors: list[str] = []
            for raw_entry in people_data:
                if use_compact:
                    if isinstance(raw_entry, list) and not raw_entry:
                        logger.warning("[PersonExtract] skipping empty compact person row")
                        continue
                    if isinstance(raw_entry, list):
                        try:
                            entry = expand_compact_person_row(raw_entry)
                        except (ValueError, TypeError) as expand_err:
                            msg = str(expand_err)
                            if is_skippable_compact_row_error(msg):
                                logger.warning(
                                    "[PersonExtract] skipping placeholder compact person row: %s",
                                    msg,
                                )
                                continue
                            parse_errors.append(msg)
                            logger.warning(
                                "[PersonExtract] skipping invalid compact person row: %s",
                                msg,
                            )
                            continue
                    elif isinstance(raw_entry, dict):
                        logger.warning(
                            "[PersonExtract] compact mode received object entry; "
                            "using full dict parse fallback"
                        )
                        entry = raw_entry
                    else:
                        parse_errors.append("person entry must be an array or object")
                        continue
                else:
                    if not isinstance(raw_entry, dict):
                        parse_errors.append("person entry must be an object")
                        continue
                    entry = raw_entry
                try:
                    people.append(person_from_llm_entry(entry))
                except (ValueError, TypeError) as entry_err:
                    msg = str(entry_err)
                    if is_skippable_compact_row_error(msg):
                        logger.warning(
                            "[PersonExtract] skipping placeholder person entry: %s",
                            msg,
                        )
                        continue
                    parse_errors.append(msg)
                    logger.warning("[PersonExtract] skipping invalid LLM person entry: %s", msg)
            if not people and parse_errors:
                detail = parse_errors[0] if len(parse_errors) == 1 else "; ".join(parse_errors[:5])
                raise ValueError(
                    f"Failed to parse LLM response as people data: no valid people. {detail}"
                )
            if not people and people_data:
                logger.info(
                    "[PersonExtract] LLM returned no qualifying people after skipping "
                    "placeholder rows"
                )

        output_data: dict[str, Any] = {
            "text": text,
            "people": [person.model_dump() for person in people],
        }

        llm_top_level_fields: dict[str, Any] = {}
        if isinstance(response_data, dict):
            for key, value in response_data.items():
                if key != "people":
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

        return PersonExtractOutput(**output_data)

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
