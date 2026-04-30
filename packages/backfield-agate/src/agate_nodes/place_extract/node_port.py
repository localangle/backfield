"""PlaceExtract node for extracting place information from text using LLM.

Description:
This node uses an LLM to process JSON data according to your custom prompt and returns structured JSON data.
Use JSON path placeholders in your prompt to extract specific fields:
  {text} - extracts the text field
  {url} - extracts the url field
  {results.images} - extracts nested results.images object/array
  {results.caption} - extracts only caption field from array elements
  {results.caption, id} - extracts multiple fields from array elements
  {raw} - passes entire input JSON
"""

import os
import asyncio
import time
import json
import re
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field, ConfigDict

from backfield_agate.context import AgateEnvContext
from agate_utils.llm import call_llm

# Get Celery timeout limits from environment (defaults match worker/tasks.py)
TASK_SOFT_TIME_LIMIT = int(os.getenv("TASK_SOFT_TIME_LIMIT", "3600"))  # 60 minutes default


class PlaceExtractInput(BaseModel):
    """Input schema - expects to find text in namespaced state."""
    model_config = ConfigDict(extra='allow')


class PlaceExtractParams(BaseModel):
    """Parameters for PlaceExtract node."""
    model: str = Field(
        default="gpt-4o-mini",
        description="LLM model to use (e.g., gpt-4o-mini, gpt-5, claude-haiku-4-5-20251001)"
    )
    prompt_file: str = Field(
        default="prompts/extract.md",
        description="Path to the prompt file relative to the node directory. Defaults to prompts/extract.md"
    )
    prompt: str = Field(
        default="",
        description="Custom prompt override. If provided, this takes precedence over prompt_file."
    )
    llmTimeout: int = Field(
        default=600,
        ge=60,
        le=1800,
        description="Timeout in seconds for the LLM call (default: 10 minutes, max: 30 minutes)"
    )


class StateInfo(BaseModel):
    """State information."""
    name: str = Field(description="Full name of the state")
    abbr: str = Field(description="Postal abbreviation for the state")


class CountryInfo(BaseModel):
    """Country information."""
    name: str = Field(description="Full name of the country")
    abbr: str = Field(description="ISO 3166-1 country code")


class StreetRoadInfo(BaseModel):
    """Street/Road information for street_road types."""
    name: str = Field(description="Name of the street")
    boundary: str = Field(description="Geocodable boundary string for the street")


class PlaceInfo(BaseModel):
    """Place information for named places."""
    name: str = Field(description="Name of the place")
    addressable: bool = Field(default=False, description="Whether the place has a findable street address")
    natural: bool = Field(default=False, description="Whether the place represents a natural location")


class SpanEndpoint(BaseModel):
    """Endpoint for a span of road."""
    type: str = Field(description="The kind of endpoint (city or intersection)")
    location: str = Field(description="Geocodable representation of the endpoint")


class SpanInfo(BaseModel):
    """Span information for span types."""
    start: Optional[SpanEndpoint] = Field(default=None, description="Span starting point")
    end: Optional[SpanEndpoint] = Field(default=None, description="Span ending point")


class LocationComponents(BaseModel):
    """Components of a location."""
    place: Optional[PlaceInfo] = Field(default=None, description="Place information if applicable")
    street_road: Optional[StreetRoadInfo] = Field(default=None, description="Street/road information if applicable")
    span: Optional[SpanInfo] = Field(default=None, description="Span information for span types")
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
    model_config = ConfigDict(extra='allow')  # Allow additional fields like 'mural'


class PlaceExtractOutput(BaseModel):
    """Output schema - returns extracted places and preserves input state."""
    model_config = ConfigDict(extra='allow')
    
    text: str = Field(description="Original input text")
    locations: List[Place] = Field(description="List of extracted locations")


class PlaceExtractNode:
    """Node for extracting place information from text using LLM."""

    name = "PlaceExtract"
    version = "0.1.0"
    category = "extraction"

    Input = PlaceExtractInput
    Output = PlaceExtractOutput
    Params = PlaceExtractParams

    def _extract_json_path(self, input_dict: Dict[str, Any], path_spec: str) -> Any:
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
        
        # Multi-field spec
        if ',' in path_spec:
            fields = [f.strip() for f in path_spec.split(',')]
            base_path = fields[0]
            additional_fields = fields[1:]
            
            # Navigate base_path
            target = self._extract_json_path(input_dict, base_path)
            all_fields = [base_path.split('.')[-1]] + additional_fields
            
            def pick_fields(obj):
                if isinstance(obj, dict):
                    return {f: obj.get(f) for f in all_fields if f in obj}
                return obj
            
            if isinstance(target, list):
                return [pick_fields(item) for item in target if isinstance(item, dict)]
            return pick_fields(target)
        
        # Simple or dotted path
        parts = path_spec.split('.')
        current: Union[Dict[str, Any], List[Any], Any] = input_dict
        for i, part in enumerate(parts):
            if isinstance(current, dict) and part in current:
                current = current[part]
            elif isinstance(current, list):
                # Extract field from each element if list
                extracted = []
                for item in current:
                    if isinstance(item, dict) and part in item:
                        extracted.append(item[part])
                current = extracted
            else:
                raise ValueError(f"Path '{'.'.join(parts[:i+1])}' not found in input")
        return current
    
    def _sanitize_for_prompt(self, value: Any) -> Any:
        """
        Remove geometry data from custom_geographies to avoid huge token costs.
        Preserves essential fields like id, label, type, city, state, etc.
        """
        if isinstance(value, dict):
            # If this is a custom geography entry, strip geometry fields
            if "geocode" in value and isinstance(value["geocode"], dict):
                result = value["geocode"].get("result", {})
                if isinstance(result, dict):
                    # Remove geometry but keep other fields
                    sanitized_result = {k: v for k, v in result.items() if k not in ["geometry", "boundaries"]}
                    sanitized_geocode = {**value["geocode"], "result": sanitized_result}
                    return {**value, "geocode": sanitized_geocode}
            # Recursively sanitize nested dicts
            return {k: self._sanitize_for_prompt(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._sanitize_for_prompt(item) for item in value]
        return value
    
    def _build_prompt(self, input_dict: Dict[str, Any], prompt_template: str) -> str:
        """
        Replace {json_path} placeholders in prompt_template using the provided input_dict.
        Skips escaped braces ({{ and }}) to avoid treating them as placeholders.
        Automatically sanitizes custom_geographies to remove geometry data.
        """
        # Temporarily replace escaped braces with markers to avoid matching them
        # Use unique markers that won't appear in the actual content
        ESCAPED_OPEN = "___ESCAPED_OPEN_BRACE___"
        ESCAPED_CLOSE = "___ESCAPED_CLOSE_BRACE___"
        
        # Replace {{ with marker
        temp_template = prompt_template.replace("{{", ESCAPED_OPEN)
        temp_template = temp_template.replace("}}", ESCAPED_CLOSE)
        
        # Now find placeholders (these will only match unescaped braces)
        placeholders = re.findall(r'\{([^}]+)\}', temp_template)
        prompt = temp_template
        
        for placeholder in placeholders:
            placeholder_key = placeholder.strip()
            try:
                value = self._extract_json_path(input_dict, placeholder_key)
                # Sanitize geometry data before serializing
                sanitized_value = self._sanitize_for_prompt(value)
                if isinstance(sanitized_value, (dict, list)):
                    serialized = json.dumps(sanitized_value, indent=2)
                elif isinstance(sanitized_value, str):
                    serialized = sanitized_value
                else:
                    serialized = json.dumps(sanitized_value)
                prompt = prompt.replace(f'{{{placeholder}}}', serialized)
            except Exception as e:
                raise ValueError(
                    f"Failed to extract JSON path '{placeholder_key}': {str(e)}\n"
                    f"Available top-level keys in input: {list(input_dict.keys())}"
                ) from e
        
        # Restore escaped braces
        prompt = prompt.replace(ESCAPED_OPEN, "{{")
        prompt = prompt.replace(ESCAPED_CLOSE, "}}")
        
        return prompt
    
    def _escape_braces(self, s: str) -> str:
        """Escape braces so they are not treated as placeholders."""
        return s.replace("{", "{{").replace("}", "}}")
    
    async def run(
        self,
        inp: PlaceExtractInput,
        params: PlaceExtractParams,
        ctx: AgateEnvContext
    ) -> PlaceExtractOutput:
        """
        Execute place extraction - extract text from namespaced state.
        """
        # Track start time for timeout calculations
        start_time = time.time()
        CELERY_TIMEOUT_BUFFER = 300  # Stop 5 minutes before Celery timeout to allow cleanup
        
        input_dict = inp.model_dump()
        
        # Flatten namespaced input to make JSON paths easier (similar to LLMEnrich)
        # Only unwrap namespaced node-* dictionaries; preserve normal dict fields (like meta_* objects)
        flattened_input: Dict[str, Any] = {}
        for key, value in input_dict.items():
            is_node_key = key.startswith("node-") and len(key) > 5 and key[5:].isdigit()
            if is_node_key and isinstance(value, dict):
                flattened_input.update(value)
            elif isinstance(value, dict):
                # Backfield executor namespaces by arbitrary upstream node ids (e.g. n1, a).
                flattened_input.update(value)
            else:
                flattened_input[key] = value
        
        # Debug logging to trace meta fields
        try:
            meta_keys = [k for k in flattened_input.keys() if k.startswith("meta_")]
            print(f"[PlaceExtract] Input keys: {list(input_dict.keys())}")
            print(f"[PlaceExtract] Flattened keys: {list(flattened_input.keys())}")
            if meta_keys:
                print(f"[PlaceExtract] Found meta_* keys: {meta_keys}")
            else:
                print(f"[PlaceExtract] WARNING: No meta_* keys in flattened_input")
        except Exception:
            pass
        
        # Prefer text from flattened input
        text = flattened_input.get("text")
        
        # Backward compatibility: try to find text in namespaced dicts if not found
        if not text:
            for node_id, node_data in input_dict.items():
                if isinstance(node_data, dict) and 'text' in node_data:
                    text = node_data['text']
                    break
        
        # If still not found, accept top-level text field even if not namespaced
        if not text and "text" in input_dict and isinstance(input_dict["text"], str):
            text = input_dict["text"]
        
        if not text:
            raise ValueError(
                f"No 'text' field found in input state. Available keys: {list(input_dict.keys())}, "
                f"Node data keys: {[list(v.keys()) if isinstance(v, dict) else 'not dict' for v in input_dict.values()]}"
            )
        
        # Use custom prompt if provided, otherwise load from prompt_file
        if params.prompt and params.prompt.strip():
            prompt_template = params.prompt
        else:
            prompt_template = self._load_prompt_template(params.prompt_file)
        
        # Build prompt using JSON path placeholders
        prompt = self._build_prompt(flattened_input, prompt_template)
        
        # Concrete JSON example (prompts/_output_format.json), after framing not kept in extract.md
        output_format = self._load_output_format_template()
        escaped_format = self._escape_braces(output_format)
        prompt = (
            f"{prompt}\n\n"
            "The results should be returned in a JSON that looks like the following.\n\n"
            f"{escaped_format}"
        )
        
        # Log the prompt for debugging
        print(f"[PlaceExtract] Prompt:\n{prompt}")
        
        # Check if we're approaching Celery timeout before making LLM call
        # Calculate elapsed time since node start
        elapsed_time = time.time() - start_time
        
        # Use a conservative estimate: assume we're already partway through the task
        # We'll use elapsed_time as a proxy, but be conservative by assuming we need buffer
        # If we've been running for more than (TASK_SOFT_TIME_LIMIT - CELERY_TIMEOUT_BUFFER), stop
        max_safe_runtime = TASK_SOFT_TIME_LIMIT - CELERY_TIMEOUT_BUFFER
        
        if elapsed_time > max_safe_runtime:
            raise TimeoutError(
                f"Node has been running for {elapsed_time:.1f}s, which exceeds safe runtime limit "
                f"({max_safe_runtime}s). Cannot safely execute PlaceExtract LLM call."
            )
        
        # Calculate effective timeout: use the smaller of user timeout or remaining safe time
        remaining_safe_time = max_safe_runtime - elapsed_time
        effective_timeout = min(params.llmTimeout, remaining_safe_time)
        
        if effective_timeout < 60:
            raise TimeoutError(
                f"Insufficient time remaining ({effective_timeout:.1f}s) for LLM call. "
                f"Need at least 60 seconds. Elapsed: {elapsed_time:.1f}s"
            )
        
        print(
            f"[PlaceExtract] Executing LLM call with timeout: {effective_timeout}s "
            f"(elapsed: {elapsed_time:.1f}s, remaining safe time: {remaining_safe_time:.1f}s)"
        )
        
        # Call the LLM with API keys from context, wrapped in asyncio timeout
        # Since call_llm is synchronous, we need to run it in a thread pool
        try:
            response_text = await asyncio.wait_for(
                asyncio.to_thread(
                    call_llm,
                    prompt=prompt,
                    model=params.model,
                    system_message=(
                        "You are a specialized AI assistant for extracting editorially relevant, "
                        "literal physical place information from news text. Return only valid JSON."
                    ),
                    force_json=True,
                    temperature=0.0,
                    timeout=effective_timeout,  # Pass timeout to call_llm as well
                    openai_api_key=ctx.get_api_key("OPENAI_API_KEY"),
                    anthropic_api_key=ctx.get_api_key("ANTHROPIC_API_KEY"),
                    project_system_prompt=ctx.project_system_prompt
                ),
                timeout=effective_timeout
            )
        except asyncio.TimeoutError:
            elapsed = time.time() - start_time
            raise TimeoutError(
                f"PlaceExtract LLM call exceeded timeout of {effective_timeout}s "
                f"(elapsed: {elapsed:.1f}s). The text may be too long or the LLM may be slow."
            )
        
        elapsed = time.time() - start_time
        print(f"[PlaceExtract] LLM call completed in {elapsed:.1f}s")
        
        # Parse the response
        import json
        response_data = None
        try:
            response_data = json.loads(response_text)
            
            # Handle both old format (direct array) and new format (with "locations" wrapper)
            if isinstance(response_data, list):
                locations_data = response_data
            elif isinstance(response_data, dict) and 'locations' in response_data:
                locations_data = response_data['locations']
            else:
                raise ValueError("Expected a list of locations or an object with 'locations' field")
            
            if not isinstance(locations_data, list):
                raise ValueError("Expected a list of locations")
            
            # Convert to Place objects - handle new format from updated prompt
            locations = []
            for location_data in locations_data:
                # Validate required fields
                required_fields = ['original_text', 'description', 'location', 'type', 'components']
                for field in required_fields:
                    if field not in location_data:
                        raise ValueError(f"Missing required field '{field}' in location data")
                
                # Handle new format: location is a string, type and components are at top level
                location_str = location_data['location']
                location_type = location_data['type']
                components_data = location_data['components']
                
                if not isinstance(location_str, str):
                    raise ValueError("Location field must be a string")
                if not isinstance(location_type, str):
                    raise ValueError("Type field must be a string")
                if not isinstance(components_data, dict):
                    raise ValueError("Components field must be a dictionary")
                
                # Validate components structure
                components = components_data
                
                # Handle optional place info
                if 'place' in components and components['place']:
                    place_data = components['place']
                    if isinstance(place_data, dict) and place_data.get('name'):
                        try:
                            components['place'] = PlaceInfo(**place_data)
                        except Exception:
                            components['place'] = None
                    else:
                        components['place'] = None
                else:
                    components['place'] = None
                
                # Handle optional street_road info
                if 'street_road' in components and components['street_road']:
                    street_road_data = components['street_road']
                    if isinstance(street_road_data, dict) and street_road_data.get('name') and street_road_data.get('boundary'):
                        components['street_road'] = StreetRoadInfo(**street_road_data)
                    else:
                        components['street_road'] = None
                else:
                    components['street_road'] = None

                # Handle optional span info
                if 'span' in components and components['span']:
                    span_data = components['span']
                    if isinstance(span_data, dict):
                        try:
                            start = span_data.get('start')
                            end = span_data.get('end')
                            components['span'] = SpanInfo(
                                start=SpanEndpoint(**start) if isinstance(start, dict) and start.get('type') and start.get('location') else None,
                                end=SpanEndpoint(**end) if isinstance(end, dict) and end.get('type') and end.get('location') else None,
                            )
                        except Exception:
                            components['span'] = None
                    else:
                        components['span'] = None
                else:
                    components['span'] = None
                
                # Handle optional state info
                if 'state' in components and components['state']:
                    state_data = components['state']
                    if isinstance(state_data, dict) and state_data.get('name') and state_data.get('abbr'):
                        components['state'] = StateInfo(**state_data)
                    else:
                        components['state'] = None
                else:
                    components['state'] = None
                
                # Handle optional country info
                if 'country' in components and components['country']:
                    country_data = components['country']
                    if isinstance(country_data, dict) and country_data.get('name') and country_data.get('abbr'):
                        components['country'] = CountryInfo(**country_data)
                    else:
                        components['country'] = None
                else:
                    components['country'] = None
                
                # Create LocationComponents object
                location_components = LocationComponents(**components)
                
                # Create LocationInfo object
                location_info_obj = LocationInfo(
                    full=location_str,
                    type=location_type,
                    components=location_components
                )
                
                # Create Place object - preserve all fields from location_data (including 'mural' and any other custom fields)
                place_data = {
                    'original_text': location_data['original_text'],
                    'description': location_data['description'],
                    'location': location_info_obj
                }
                
                # Preserve any additional fields from the LLM response (like 'mural')
                for key, value in location_data.items():
                    if key not in ['original_text', 'description', 'location', 'type', 'components']:
                        place_data[key] = value
                
                locations.append(Place(**place_data))
            
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            raise ValueError(f"Failed to parse LLM response as location data: {e}")
        
        # Create output with extraction results
        output_data = {
            "text": text,
            "locations": [location.model_dump() for location in locations]
        }
        
        # Handle top-level fields from LLM response (if response_data is a dict with fields beyond 'locations')
        # Store these temporarily to check against meta_* fields
        llm_top_level_fields = {}
        if isinstance(response_data, dict):
            for key, value in response_data.items():
                if key != "locations":
                    llm_top_level_fields[key] = value
                    try:
                        print(f"[PlaceExtract] LLM top-level field: {key} (type={type(value).__name__})")
                    except Exception:
                        pass
        
        # Preserve any additional fields from flattened input (like url, headline, meta_* fields, etc. from upstream nodes)
        # Priority: meta_* fields from flattened_input > LLM top-level fields > other flattened_input fields
        for key, value in flattened_input.items():
            if key not in ["text"]:  # Don't override the text field
                # Always preserve meta_* fields from flattened_input (they take highest priority)
                if key.startswith("meta_"):
                    output_data[key] = value
                    try:
                        print(f"[PlaceExtract] Preserved meta field: {key} (type={type(value).__name__})")
                    except Exception:
                        pass
                elif key not in output_data:
                    # For non-meta fields, only add if not already present
                    output_data[key] = value
        
        # Add LLM top-level fields only if they don't conflict with meta_* fields
        for key, value in llm_top_level_fields.items():
            meta_key = f"meta_{key}"
            if meta_key not in flattened_input and key not in output_data:
                output_data[key] = value
                try:
                    print(f"[PlaceExtract] Added LLM field: {key} (type={type(value).__name__})")
                except Exception:
                    pass
        
        # Also preserve fields from namespaced input state (like embedding from Embed node)
        for node_id, node_data in input_dict.items():
            if isinstance(node_data, dict):
                for key, value in node_data.items():
                    if key not in ["text"] and key not in output_data:  # Don't override existing fields
                        output_data[key] = value
        
        return PlaceExtractOutput(**output_data)
    
    def _load_prompt_template(self, prompt_file_path: str) -> str:
        """Load the prompt template from the prompts directory."""
        # Get the directory of this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Resolve path relative to node directory
        if os.path.isabs(prompt_file_path):
            prompt_file = prompt_file_path
        else:
            prompt_file = os.path.join(current_dir, prompt_file_path)
        
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Prompt template not found at {prompt_file}")
        except Exception as e:
            raise Exception(f"Failed to load prompt template: {e}")

    def _load_output_format_template(self) -> str:
        """Load the canonical JSON output example appended to every PlaceExtract prompt."""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(current_dir, "prompts", "_output_format.json")
        try:
            with open(path, encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            raise FileNotFoundError(f"Output format template not found at {path}") from None
