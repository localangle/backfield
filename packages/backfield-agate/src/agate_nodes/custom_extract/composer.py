"""Prompt assembly for Custom Extract (generated around the declared field schema)."""

from __future__ import annotations

import json
from typing import Any

from agate_runtime.upstream_input import flatten_upstream_inputs

from agate_nodes.custom_extract.schema import CustomFieldSpec, CustomRecordSchema

_FIELD_TYPE_PROMPT_HINTS: dict[str, str] = {
    "string": "a short text value",
    "number": "a number",
    "boolean": "true or false",
    "date": "an ISO date such as 2026-06-10",
    "string_list": "an array of short text values",
}


def flatten_input(input_dict: dict[str, Any]) -> dict[str, Any]:
    return flatten_upstream_inputs(input_dict)


def resolve_text(flattened: dict[str, Any]) -> str:
    text = flattened.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    raise ValueError(
        "No non-empty 'text' field found in upstream input. "
        f"Available keys: {sorted(flattened.keys())}"
    )


def _field_lines(fields: list[CustomFieldSpec]) -> str:
    lines: list[str] = []
    for spec in fields:
        hint = _FIELD_TYPE_PROMPT_HINTS[spec.type]
        description = f" {spec.description.strip()}" if spec.description.strip() else ""
        lines.append(f'- "{spec.name}" ({spec.label}): {hint}.{description}')
    return "\n".join(lines)


def _example_record(fields: list[CustomFieldSpec]) -> dict[str, Any]:
    example_values: dict[str, Any] = {
        "string": "example value",
        "number": 2.0,
        "boolean": True,
        "date": "2026-06-10",
        "string_list": ["first value", "second value"],
    }
    return {
        "fields": {spec.name: example_values[spec.type] for spec in fields},
        "mentions": [{"text": "exact passage from the article"}],
        "confidence": 0.9,
    }


def compose_custom_extract_prompt(
    *,
    record_schema: CustomRecordSchema,
    instructions: str,
    text: str,
) -> str:
    """Build the full extraction prompt with a strict JSON contract."""
    example_shape = json.dumps({"records": [_example_record(record_schema.fields)]}, indent=2)
    extra_instructions = instructions.strip()
    instructions_block = (
        f"## Extraction instructions\n\n{extra_instructions}\n\n" if extra_instructions else ""
    )
    return (
        f"# {record_schema.label} extraction\n\n"
        f"Extract every distinct record of type \"{record_schema.record_type}\" "
        "from the article text at the end of this prompt.\n\n"
        "## Fields per record\n\n"
        f"{_field_lines(record_schema.fields)}\n\n"
        f"{instructions_block}"
        "## Output\n\n"
        'Return only a valid JSON object with a single "records" key containing an array.\n'
        'Each record must be an object with exactly these keys: "fields", "mentions", '
        'and optionally "confidence".\n'
        '- "fields" holds the field values listed above; use null when a value is not '
        "stated in the article. Never guess.\n"
        '- "mentions" must contain at least one object with "text" (a verbatim snippet '
        "from the article that supports this record). Records without supporting text in "
        "the article must be omitted.\n"
        '- "confidence" is a number from 0.0 to 1.0.\n'
        "- Return an empty array when no records of this type appear in the article.\n\n"
        "Example shape:\n"
        f"{example_shape}\n\n"
        "## Text to analyze\n\n"
        f"{text}\n"
    )
