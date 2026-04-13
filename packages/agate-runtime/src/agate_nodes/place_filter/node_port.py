"""PlaceFilter node for filtering locations from PlaceExtract based on LLM relevance judgments.

Ported from agate-ai-platform `flowbuilder_nodes/place_filter/node.py`, adapted for Backfield:
`AgateEnvContext`, `agate_utils.llm.call_llm`, namespaced-input flattening aligned with PlaceExtract,
and asyncio timeouts around the synchronous LLM call.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from agate_runtime.context import AgateEnvContext
from agate_utils.llm import call_llm

logger = logging.getLogger(__name__)

TASK_SOFT_TIME_LIMIT = int(os.getenv("TASK_SOFT_TIME_LIMIT", "3600"))
CELERY_TIMEOUT_BUFFER = 300


class PlaceFilterInput(BaseModel):
    """Input schema - expects to find locations in namespaced state."""

    model_config = ConfigDict(extra="allow")


class PlaceFilterParams(BaseModel):
    """Parameters for PlaceFilter node."""

    model: str = Field(
        default="gpt-5",
        description="LLM model to use (e.g., gpt-4o-mini, gpt-5, claude-haiku-4-5-20251001)",
    )
    prompt_file: str = Field(
        default="prompts/filter.md",
        description="Path to the prompt file relative to the node directory. Defaults to prompts/filter.md",
    )
    output_format_file: str = Field(
        default="prompts/_filter_output.md",
        description="Path to the output format file relative to the node directory.",
    )
    prompt: str = Field(
        default="",
        description="Custom prompt override. If provided, this takes precedence over prompt_file.",
    )
    json_format: str = Field(
        default='[{"index":0,"relevant":true,"reason":""}]',
        description="Example output JSON format. Braces will be escaped automatically in the prompt.",
    )
    llmTimeout: int = Field(
        default=600,
        ge=60,
        le=1800,
        description="Timeout in seconds for the LLM call (default: 10 minutes, max: 30 minutes)",
    )


class StateInfo(BaseModel):
    """State information."""

    name: str = Field(description="Full name of the state")
    abbr: str = Field(description="Postal abbreviation for the state")


class CountryInfo(BaseModel):
    """Country information."""

    name: str = Field(description="Full name of the country")
    abbr: str = Field(description="ISO 3166-1 country code")


class PlaceInfo(BaseModel):
    """Place information for named places."""

    name: str = Field(description="Name of the place")
    addressable: bool = Field(default=False, description="Whether the place has a findable street address")
    natural: bool = Field(default=False, description="Whether the place represents a natural location")


class StreetRoadInfo(BaseModel):
    """Street/road information."""

    name: str = Field(description="Name of the street")
    boundary: str = Field(default="", description="Geocodable boundary containing the street")


class SpanEndpoint(BaseModel):
    """Endpoint for a roadway span."""

    type: str = Field(description="Endpoint type (city or intersection)")
    location: str = Field(description="Geocodable representation of the endpoint")


class SpanInfo(BaseModel):
    """Span information for roadway sections."""

    start: Optional[SpanEndpoint] = Field(default=None, description="Starting endpoint")
    end: Optional[SpanEndpoint] = Field(default=None, description="Ending endpoint")


class LocationComponents(BaseModel):
    """Components of a location."""

    place: Optional[PlaceInfo] = Field(default=None, description="Place information if applicable")
    street_road: Optional[StreetRoadInfo] = Field(default=None, description="Street/road information if applicable")
    span: Optional[SpanInfo] = Field(default=None, description="Span information if applicable")
    address: Optional[str] = Field(default="", description="Street address if applicable")
    neighborhood: Optional[str] = Field(default="", description="Neighborhood name if applicable")
    city: Optional[str] = Field(default="", description="City name if applicable")
    county: Optional[str] = Field(default="", description="County name if applicable")
    state: Optional[StateInfo] = Field(default=None, description="State information if applicable")
    country: Optional[CountryInfo] = Field(default=None, description="Country information if applicable")


class LocationInfo(BaseModel):
    """Location information."""

    full: str = Field(description="The full geocodable location string")
    type: str = Field(description="The type of location (e.g., city, address, intersection_road)")
    components: LocationComponents = Field(description="Detailed components of the location")


class Place(BaseModel):
    """A place extracted from text."""

    original_text: str = Field(description="The original text from which this location was extracted")
    description: str = Field(description="Brief description of the location and its relevance")
    location: LocationInfo = Field(description="Location information with components")


class PlaceFilterOutput(BaseModel):
    """Output schema - returns filtered places and preserves input state."""

    model_config = ConfigDict(extra="allow")

    text: str = Field(description="Original input text")
    locations: List[Place] = Field(description="List of filtered locations")


class PlaceFilterNode:
    """Node for filtering locations from PlaceExtract based on LLM relevance judgments."""

    name = "PlaceFilter"
    version = "0.1.0"
    category = "filter"

    Input = PlaceFilterInput
    Output = PlaceFilterOutput
    Params = PlaceFilterParams

    def _flatten_namespaced_input(self, input_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Match PlaceExtract: unwrap per-upstream namespaces for JSON path placeholders."""
        flattened_input: Dict[str, Any] = {}
        for key, value in input_dict.items():
            is_node_key = key.startswith("node-") and len(key) > 5 and key[5:].isdigit()
            if is_node_key and isinstance(value, dict):
                flattened_input.update(value)
            elif isinstance(value, dict):
                flattened_input.update(value)
            else:
                flattened_input[key] = value
        return flattened_input

    def _extract_json_path(self, input_dict: Dict[str, Any], path_spec: str) -> Any:
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
        current: Union[Dict[str, Any], List[Any], Any] = input_dict
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
        if isinstance(value, dict):
            if "geocode" in value and isinstance(value["geocode"], dict):
                result = value["geocode"].get("result", {})
                if isinstance(result, dict):
                    sanitized_result = {k: v for k, v in result.items() if k not in ["geometry", "boundaries"]}
                    sanitized_geocode = {**value["geocode"], "result": sanitized_result}
                    return {**value, "geocode": sanitized_geocode}
            return {k: self._sanitize_for_prompt(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._sanitize_for_prompt(item) for item in value]
        return value

    def _build_prompt(self, input_dict: Dict[str, Any], prompt_template: str) -> str:
        ESCAPED_OPEN = "___ESCAPED_OPEN_BRACE___"
        ESCAPED_CLOSE = "___ESCAPED_CLOSE_BRACE___"

        temp_template = prompt_template.replace("{{", ESCAPED_OPEN)
        temp_template = temp_template.replace("}}", ESCAPED_CLOSE)

        placeholders = re.findall(r"\{([^}]+)\}", temp_template)
        prompt = temp_template

        for placeholder in placeholders:
            placeholder_key = placeholder.strip()
            try:
                value = self._extract_json_path(input_dict, placeholder_key)
                sanitized_value = self._sanitize_for_prompt(value)
                if isinstance(sanitized_value, (dict, list)):
                    serialized = json.dumps(sanitized_value, indent=2)
                elif isinstance(sanitized_value, str):
                    serialized = sanitized_value
                else:
                    serialized = json.dumps(sanitized_value)
                prompt = prompt.replace(f"{{{placeholder}}}", serialized)
            except Exception as e:
                raise ValueError(
                    f"Failed to extract JSON path '{placeholder_key}': {e!s}\n"
                    f"Available top-level keys in input: {list(input_dict.keys())}"
                ) from e

        prompt = prompt.replace(ESCAPED_OPEN, "{{")
        prompt = prompt.replace(ESCAPED_CLOSE, "}}")

        return prompt

    def _escape_braces(self, s: str) -> str:
        return s.replace("{", "{{").replace("}", "}}")

    async def run(
        self,
        inp: PlaceFilterInput,
        params: PlaceFilterParams,
        ctx: AgateEnvContext,
    ) -> PlaceFilterOutput:
        start_time = time.time()
        input_dict = inp.model_dump()
        flattened_input = self._flatten_namespaced_input(input_dict)

        text = flattened_input.get("text")
        locations = flattened_input.get("locations")

        if text is None or locations is None:
            for _node_id, node_data in input_dict.items():
                if isinstance(node_data, dict):
                    if text is None and "text" in node_data:
                        text = node_data["text"]
                    if locations is None and "locations" in node_data:
                        locations = node_data["locations"]

        if not text:
            raise ValueError("No 'text' field found in input state")

        if not locations:
            return PlaceFilterOutput(text=text, locations=[])

        if not isinstance(locations, list):
            raise ValueError("Locations field must be a list")

        if len(locations) == 0:
            return PlaceFilterOutput(text=text, locations=[])

        flattened_input["locations"] = locations

        if params.prompt and params.prompt.strip():
            prompt_template = params.prompt
        else:
            prompt_template = self._load_prompt_template(params.prompt_file)

        try:
            if params.json_format:
                output_format = params.json_format
            else:
                output_format = self._load_prompt_template(params.output_format_file)
            escaped_format = self._escape_braces(output_format)
            full_prompt_template = prompt_template + "\n\n" + escaped_format
        except (FileNotFoundError, OSError) as e:
            logger.warning("Failed to load output format file: %s. Using prompt without output format.", e)
            full_prompt_template = prompt_template

        prompt = self._build_prompt(flattened_input, full_prompt_template)
        logger.info("[PlaceFilter] Prompt:\n%s", prompt)

        elapsed_time = time.time() - start_time
        max_safe_runtime = TASK_SOFT_TIME_LIMIT - CELERY_TIMEOUT_BUFFER
        if elapsed_time > max_safe_runtime:
            raise TimeoutError(
                f"Node has been running for {elapsed_time:.1f}s, which exceeds safe runtime limit "
                f"({max_safe_runtime}s). Cannot safely execute PlaceFilter LLM call."
            )

        remaining_safe_time = max_safe_runtime - elapsed_time
        effective_timeout = min(params.llmTimeout, remaining_safe_time)
        if effective_timeout < 60:
            raise TimeoutError(
                f"Insufficient time remaining ({effective_timeout:.1f}s) for LLM call. "
                f"Need at least 60 seconds. Elapsed: {elapsed_time:.1f}s"
            )

        try:
            response_text = await asyncio.wait_for(
                asyncio.to_thread(
                    call_llm,
                    prompt=prompt,
                    model=params.model,
                    system_message=(
                        "You are a specialized AI assistant for filtering place information. "
                        "Return only valid JSON."
                    ),
                    force_json=True,
                    temperature=0.0,
                    timeout=effective_timeout,
                    openai_api_key=ctx.get_api_key("OPENAI_API_KEY"),
                    anthropic_api_key=ctx.get_api_key("ANTHROPIC_API_KEY"),
                    project_system_prompt=ctx.project_system_prompt,
                ),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError as e:
            elapsed = time.time() - start_time
            raise TimeoutError(
                f"PlaceFilter LLM call exceeded timeout of {effective_timeout}s "
                f"(elapsed: {elapsed:.1f}s)."
            ) from e

        try:
            judgments = json.loads(response_text)

            if not isinstance(judgments, list):
                raise ValueError("Expected a list of judgments")

            for i, judgment in enumerate(judgments):
                if not isinstance(judgment, dict):
                    raise ValueError(f"Judgment {i} must be a dictionary")
                if "index" not in judgment or "relevant" not in judgment:
                    raise ValueError(f"Judgment {i} must have 'index' and 'relevant' fields")
                if not isinstance(judgment["index"], int):
                    raise ValueError(f"Judgment {i} index must be an integer")
                if not isinstance(judgment["relevant"], bool):
                    raise ValueError(f"Judgment {i} relevant must be a boolean")

            filtered_locations: List[Place] = []
            for judgment in judgments:
                if judgment["relevant"] and 0 <= judgment["index"] < len(locations):
                    location_data = locations[judgment["index"]]
                    filtered_locations.append(self._convert_place(location_data))

        except (json.JSONDecodeError, ValueError, TypeError) as e:
            raise ValueError(f"Failed to parse LLM response as judgment data: {e}") from e

        output_data: Dict[str, Any] = {
            "text": text,
            "locations": [location.model_dump() for location in filtered_locations],
        }

        for _node_id, node_data in input_dict.items():
            if isinstance(node_data, dict):
                for key, value in node_data.items():
                    if key not in ["text", "locations"]:
                        output_data[key] = value

        return PlaceFilterOutput(**output_data)

    def _convert_place(self, location_data: dict) -> Place:
        if "location" in location_data and isinstance(location_data["location"], str):
            location_str = location_data["location"]
            location_type = location_data.get("type", "other")
            components_data = location_data.get("components")
        elif "location" in location_data and isinstance(location_data["location"], dict):
            location_obj = location_data["location"]
            location_str = location_obj.get("full", "")
            location_type = location_obj.get("type", "other")
            components_data = location_obj.get("components")
        else:
            location_str = location_data.get("location", "")
            location_type = location_data.get("type", "other")
            components_data = None

        if components_data is None:
            components_data = {}

        place_info: Optional[PlaceInfo] = None
        street_info: Optional[StreetRoadInfo] = None
        span_info: Optional[SpanInfo] = None
        state_info: Optional[StateInfo] = None
        country_info: Optional[CountryInfo] = None

        place_data = components_data.get("place")
        if isinstance(place_data, dict) and place_data.get("name") and str(place_data.get("name", "")).strip():
            place_info = PlaceInfo(
                name=place_data["name"],
                addressable=place_data.get("addressable", False),
                natural=place_data.get("natural", False),
            )

        street_data = components_data.get("street_road")
        if isinstance(street_data, dict) and street_data.get("name") and str(street_data.get("name", "")).strip():
            street_info = StreetRoadInfo(
                name=street_data["name"],
                boundary=street_data.get("boundary", ""),
            )

        span_data = components_data.get("span")
        if isinstance(span_data, dict):
            start_data = span_data.get("start")
            end_data = span_data.get("end")
            start = None
            end = None
            if isinstance(start_data, dict) and start_data.get("type") and start_data.get("location"):
                start = SpanEndpoint(type=start_data["type"], location=start_data["location"])
            if isinstance(end_data, dict) and end_data.get("type") and end_data.get("location"):
                end = SpanEndpoint(type=end_data["type"], location=end_data["location"])
            if start or end:
                span_info = SpanInfo(start=start, end=end)

        state_data = components_data.get("state")
        if isinstance(state_data, dict) and state_data.get("name") and str(state_data.get("name", "")).strip():
            state_info = StateInfo(
                name=state_data["name"],
                abbr=state_data.get("abbr", ""),
            )

        country_data = components_data.get("country")
        if isinstance(country_data, dict) and country_data.get("name") and str(country_data.get("name", "")).strip():
            country_info = CountryInfo(
                name=country_data["name"],
                abbr=country_data.get("abbr", ""),
            )

        components = LocationComponents(
            place=place_info,
            street_road=street_info,
            span=span_info,
            address=components_data.get("address", ""),
            neighborhood=components_data.get("neighborhood", ""),
            city=components_data.get("city", ""),
            county=components_data.get("county", ""),
            state=state_info,
            country=country_info,
        )

        location_info = LocationInfo(full=location_str, type=location_type, components=components)

        return Place(
            original_text=location_data.get("original_text", ""),
            description=location_data.get("description", ""),
            location=location_info,
        )

    def _load_prompt_template(self, prompt_file_path: str) -> str:
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
