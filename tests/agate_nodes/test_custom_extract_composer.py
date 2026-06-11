"""Tests for Custom Extract prompt composition."""

from __future__ import annotations

from agate_nodes.custom_extract.composer import compose_custom_extract_prompt
from agate_nodes.custom_extract.schema import CustomRecordSchema


def _schema() -> CustomRecordSchema:
    return CustomRecordSchema(
        record_type="ingredients",
        label="Ingredients",
        fields=[
            {"name": "item", "label": "Item", "type": "string", "description": "Ingredient name."},
            {"name": "quantity", "label": "Quantity", "type": "string"},
        ],
    )


def test_prompt_includes_field_contract_and_text() -> None:
    prompt = compose_custom_extract_prompt(
        record_schema=_schema(),
        instructions="Only the recipe card, not the narrative.",
        text="Mix 2 cups of flour with a pinch of salt.",
    )
    assert '"item" (Item): a short text value. Ingredient name.' in prompt
    assert '"quantity" (Quantity)' in prompt
    assert "Only the recipe card, not the narrative." in prompt
    assert '"records"' in prompt
    assert "Mix 2 cups of flour with a pinch of salt." in prompt
    assert "at least one object" in prompt
    assert '"quote"' not in prompt


def test_prompt_omits_instructions_block_when_empty() -> None:
    prompt = compose_custom_extract_prompt(
        record_schema=_schema(),
        instructions="   ",
        text="Article body.",
    )
    assert "## Extraction instructions" not in prompt
