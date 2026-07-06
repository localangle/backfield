"""PlaceExtract prompt source resolution and placeholder substitution."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any


def normalize_prompt_for_comparison(text: str) -> str:
    """Compare bundled vs graph-saved prompts ignoring brace-escape drift."""
    normalized = text.strip()
    normalized = re.sub(r"\{\{([^}]+)\}\}", r"{\1}", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def resolve_place_extract_prompt(*, bundled: str, custom: str | None) -> str:
    """Prefer the live bundled prompt when a saved graph still carries an old snapshot."""
    custom_stripped = (custom or "").strip()
    if not custom_stripped:
        return bundled
    if normalize_prompt_for_comparison(custom_stripped) == normalize_prompt_for_comparison(
        bundled
    ):
        return bundled
    return custom_stripped


def substitute_prompt_placeholders(
    template: str,
    input_dict: dict[str, Any],
    *,
    extract_json_path: Callable[[dict[str, Any], str], Any],
) -> str:
    """Replace ``{token}`` placeholders when present in input; leave others literal."""
    esc_open = "___ESCAPED_OPEN_BRACE___"
    esc_close = "___ESCAPED_CLOSE_BRACE___"
    temp_template = template.replace("{{", esc_open).replace("}}", esc_close)
    placeholders = re.findall(r"\{([^}]+)\}", temp_template)
    prompt = temp_template
    for placeholder in placeholders:
        placeholder_key = placeholder.strip()
        try:
            value = extract_json_path(input_dict, placeholder_key)
        except Exception:
            continue
        if isinstance(value, (dict, list)):
            serialized = json.dumps(value, indent=2)
        elif isinstance(value, str):
            serialized = value
        else:
            serialized = json.dumps(value)
        prompt = prompt.replace(f"{{{placeholder}}}", serialized)
    return prompt.replace(esc_open, "{{").replace(esc_close, "}}")
