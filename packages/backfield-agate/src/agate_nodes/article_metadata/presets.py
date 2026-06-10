"""Article Metadata preset identifiers and meta_type mapping."""

from __future__ import annotations

from typing import Literal

PromptPresetId = Literal[
    "topic",
    "subject",
    "temporal_orientation",
    "format",
    "geographic_scope",
    "information_needs",
    "jobs_to_be_done",
    "custom",
]

PRESET_IDS: tuple[str, ...] = (
    "topic",
    "subject",
    "temporal_orientation",
    "format",
    "geographic_scope",
    "information_needs",
    "jobs_to_be_done",
    "custom",
)

MULTI_VALUE_PRESET_IDS: frozenset[str] = frozenset({"subject", "information_needs"})
MAX_MULTI_VALUE_COUNT = 3

MULTI_VALUE_LIST_KEYS: dict[str, str] = {
    "subject": "subjects",
    "information_needs": "needs",
}

PRESET_LABELS: dict[str, str] = {
    "topic": "Topic",
    "subject": "Subject",
    "temporal_orientation": "Timeframe",
    "format": "Format",
    "geographic_scope": "Scope",
    "information_needs": "Critical information need",
    "jobs_to_be_done": "Jobs to be done",
    "custom": "Custom",
}


def normalize_prompt_preset(raw: str | None) -> str:
    preset = (raw or "topic").strip().lower().replace("-", "_")
    if preset in PRESET_IDS:
        return preset
    return "topic"


def meta_type_for_preset(preset_id: str) -> str:
    if preset_id == "custom":
        return "custom"
    return preset_id


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
