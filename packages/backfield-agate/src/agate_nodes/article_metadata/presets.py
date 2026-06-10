"""Article Metadata preset identifiers and meta_type mapping."""

from __future__ import annotations

from typing import Literal

PromptPresetId = Literal[
    "topic",
    "temporal_orientation",
    "geographic_scope",
    "information_needs",
    "jobs_to_be_done",
    "custom",
]

PRESET_IDS: tuple[str, ...] = (
    "topic",
    "temporal_orientation",
    "geographic_scope",
    "information_needs",
    "jobs_to_be_done",
    "custom",
)

PRESET_LABELS: dict[str, str] = {
    "topic": "Topic",
    "temporal_orientation": "Temporal orientation",
    "geographic_scope": "Geographic scope",
    "information_needs": "Information needs",
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
