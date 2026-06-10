"""Article Metadata preset identifiers and meta_type mapping."""

from __future__ import annotations

import re
from typing import Literal

DEFAULT_PROMPT_PRESET = "subject"

_META_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

PromptPresetId = Literal[
    "subject",
    "temporal_orientation",
    "format",
    "geographic_scope",
    "information_needs",
    "user_need",
    "custom",
]

PRESET_IDS: tuple[str, ...] = (
    "subject",
    "temporal_orientation",
    "format",
    "geographic_scope",
    "information_needs",
    "user_need",
    "custom",
)

MULTI_VALUE_PRESET_IDS: frozenset[str] = frozenset({"subject", "information_needs"})
MAX_MULTI_VALUE_COUNT = 3

MULTI_VALUE_LIST_KEYS: dict[str, str] = {
    "subject": "subjects",
    "information_needs": "needs",
}

PRESET_LABELS: dict[str, str] = {
    "subject": "Subject",
    "temporal_orientation": "Timeframe",
    "format": "Format",
    "geographic_scope": "Scope",
    "information_needs": "Critical information need",
    "user_need": "User need",
    "custom": "Custom",
}


def normalize_prompt_preset(raw: str | None) -> str:
    preset = (raw or DEFAULT_PROMPT_PRESET).strip().lower().replace("-", "_")
    if preset in PRESET_IDS:
        return preset
    return DEFAULT_PROMPT_PRESET


def meta_type_for_preset(preset_id: str) -> str:
    if preset_id == "custom":
        return "custom"
    return preset_id


def normalize_custom_meta_type(raw: str | None) -> str:
    """Validate a user-defined metadata dimension key for the custom preset."""
    value = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not value:
        raise ValueError(
            "Custom preset requires a metadata type (for example brand_safety)."
        )
    if not _META_TYPE_PATTERN.match(value):
        raise ValueError(
            "Metadata type must start with a letter and use only lowercase letters, "
            "numbers, and underscores."
        )
    reserved = {preset for preset in PRESET_IDS if preset != "custom"}
    if value in reserved:
        raise ValueError(
            f"Metadata type {value!r} is reserved for a built-in preset; choose a different name."
        )
    return value


def resolve_meta_type(preset_id: str, *, custom_meta_type: str | None = None) -> str:
    if preset_id == "custom":
        return normalize_custom_meta_type(custom_meta_type)
    return meta_type_for_preset(preset_id)


def preset_prompt_relpath(preset_id: str) -> str | None:
    if preset_id == "custom":
        return None
    return f"prompts/presets/{preset_id}.md"


def preset_output_format_relpath(preset_id: str) -> str:
    if preset_id in MULTI_VALUE_PRESET_IDS:
        return "prompts/_output_format_subject.json"
    return "prompts/_output_format.json"


def is_multi_value_preset(preset_id: str) -> bool:
    return preset_id in MULTI_VALUE_PRESET_IDS


def multi_value_list_key(preset_id: str) -> str:
    return MULTI_VALUE_LIST_KEYS[preset_id]
