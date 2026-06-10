"""Prompt assembly and category list extraction for Article Metadata."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from agate_nodes.article_metadata.presets import MAX_MULTI_VALUE_COUNT, multi_value_list_key

_CATEGORIES_HEADER = "## categories"


def flatten_input(input_dict: dict[str, Any]) -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in input_dict.items():
        is_node_key = key.startswith("node-") and len(key) > 5 and key[5:].isdigit()
        if is_node_key and isinstance(value, dict):
            flattened.update(value)
        elif isinstance(value, dict):
            flattened.update(value)
        else:
            flattened[key] = value
    return flattened


def resolve_text(flattened: dict[str, Any]) -> str:
    text = flattened.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    raise ValueError(
        "No non-empty 'text' field found in upstream input. "
        f"Available keys: {sorted(flattened.keys())}"
    )


def extract_categories_from_prompt(prompt: str) -> list[str]:
    """Parse bullet labels under a ``## Categories`` markdown section."""
    lines = prompt.splitlines()
    in_section = False
    categories: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.lower().startswith(_CATEGORIES_HEADER):
            in_section = True
            continue
        if in_section and stripped.startswith("## "):
            break
        if not in_section:
            continue
        for prefix in ("- ", "* "):
            if stripped.startswith(prefix):
                label = stripped[len(prefix) :].strip()
                if label and label not in categories:
                    categories.append(label)
                break
    if not categories:
        raise ValueError(
            "Prompt must include a ## Categories section with at least one bullet label."
        )
    return categories


def substitute_prompt_placeholders(template: str, flattened: dict[str, Any]) -> str:
    esc_open = "___ESCAPED_OPEN_BRACE___"
    esc_close = "___ESCAPED_CLOSE_BRACE___"
    temp = template.replace("{{", esc_open).replace("}}", esc_close)
    placeholders = re.findall(r"\{([^}]+)\}", temp)
    prompt = temp
    for placeholder in placeholders:
        key = placeholder.strip()
        value = flattened.get(key)
        if value is None:
            serialized = ""
        elif isinstance(value, (dict, list)):
            serialized = json.dumps(value, indent=2)
        elif isinstance(value, str):
            serialized = value
        else:
            serialized = json.dumps(value)
        prompt = prompt.replace(f"{{{placeholder}}}", serialized)
    return prompt.replace(esc_open, "{{").replace(esc_close, "}}")


def load_package_file(relpath: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    path = relpath if os.path.isabs(relpath) else os.path.join(base_dir, relpath)
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def compose_article_metadata_prompt(
    *,
    prompt_template: str,
    flattened: dict[str, Any],
    output_format_json: str,
    preset_id: str = "subject",
) -> tuple[str, list[str]]:
    body = substitute_prompt_placeholders(prompt_template, flattened)
    categories = extract_categories_from_prompt(body)
    if preset_id in {"subject", "information_needs"}:
        list_key = multi_value_list_key(preset_id)
        try:
            items_example = json.loads(output_format_json.strip())
        except json.JSONDecodeError:
            items_example = []
        example_shape = json.dumps({list_key: items_example}, indent=2)
        prompt = (
            f"{body.rstrip()}\n\n"
            f'Return only valid JSON object with a "{list_key}" key containing '
            f"an array of 1 to {MAX_MULTI_VALUE_COUNT} objects.\n"
            "Each object must have exactly these keys: category, rationale, confidence.\n"
            "- category must be one of the labels listed under ## Categories.\n"
            "- rationale is a concise explanation for editors.\n"
            "- confidence is a number from 0.0 to 1.0.\n"
            "- Do not repeat the same category.\n\n"
            "Example shape:\n"
            f"{example_shape}\n"
        )
    else:
        prompt = (
            f"{body.rstrip()}\n\n"
            "Return only valid JSON with exactly these keys: category, rationale, confidence.\n"
            "- category must be one of the labels listed under ## Categories.\n"
            "- rationale is a concise explanation for editors.\n"
            "- confidence is a number from 0.0 to 1.0.\n\n"
            "Example shape:\n"
            f"{output_format_json.strip()}\n"
        )
    return prompt, categories
