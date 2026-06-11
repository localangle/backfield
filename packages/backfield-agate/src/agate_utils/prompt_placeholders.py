"""Substitute ``{json.path}`` tokens in prompt templates from upstream input."""

from __future__ import annotations

import json
import re
from typing import Any


def extract_json_path(input_dict: dict[str, Any], path_spec: str) -> Any:
    """Resolve one placeholder path against flattened upstream input."""
    if path_spec == "raw":
        return input_dict

    if "," in path_spec:
        fields = [field.strip() for field in path_spec.split(",")]
        base_path = fields[0]
        additional_fields = fields[1:]

        if "." in base_path:
            parts = base_path.split(".")
            current: dict[str, Any] | list[Any] | Any = input_dict
            for part in parts[:-1]:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    raise ValueError(f"Path '{'.'.join(parts[:-1])}' not found in input")

            first_field = parts[-1]
            if isinstance(current, list):
                all_fields = [first_field, *additional_fields]
                return [
                    {field: item.get(field) for field in all_fields if field in item}
                    for item in current
                    if isinstance(item, dict)
                ]
            if isinstance(current, dict):
                all_fields = [first_field, *additional_fields]
                return {field: current.get(field) for field in all_fields if field in current}
            raise ValueError(f"Cannot extract fields from non-object: {type(current)}")

        all_fields = [base_path, *additional_fields]
        return {field: input_dict.get(field) for field in all_fields if field in input_dict}

    if "." not in path_spec:
        if path_spec not in input_dict:
            raise ValueError(f"Field '{path_spec}' not found in input")
        return input_dict[path_spec]

    parts = path_spec.split(".")
    current: dict[str, Any] | list[Any] | Any = input_dict
    for index, part in enumerate(parts[:-1]):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise ValueError(f"Path '{'.'.join(parts[: index + 1])}' not found in input")

    last_part = parts[-1]
    if isinstance(current, list):
        return [
            {last_part: item[last_part]}
            for item in current
            if isinstance(item, dict) and last_part in item
        ]
    if isinstance(current, dict):
        if last_part not in current:
            raise ValueError(f"Field '{path_spec}' not found in input")
        return current[last_part]
    raise ValueError(f"Cannot access field '{last_part}' of {type(current)}")


def substitute_prompt_placeholders(template: str, input_dict: dict[str, Any]) -> str:
    """Replace ``{token}`` placeholders; ``{{`` and ``}}`` stay literal."""
    esc_open = "___ESCAPED_OPEN_BRACE___"
    esc_close = "___ESCAPED_CLOSE_BRACE___"
    temp_template = template.replace("{{", esc_open).replace("}}", esc_close)
    placeholders = re.findall(r"\{([^}]+)\}", temp_template)
    prompt = temp_template
    for placeholder in placeholders:
        placeholder_key = placeholder.strip()
        value = extract_json_path(input_dict, placeholder_key)
        if isinstance(value, (dict, list)):
            serialized = json.dumps(value, indent=2)
        elif isinstance(value, str):
            serialized = value
        else:
            serialized = json.dumps(value)
        prompt = prompt.replace(f"{{{placeholder}}}", serialized)
    return prompt.replace(esc_open, "{{").replace(esc_close, "}}")
