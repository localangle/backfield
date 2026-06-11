"""Tests for Custom Extract schema params and dynamic record model."""

from __future__ import annotations

import pytest
from agate_nodes.custom_extract.schema import (
    CustomFieldSpec,
    CustomRecordSchema,
    build_record_fields_model,
)
from pydantic import ValidationError


def _ingredients_schema() -> CustomRecordSchema:
    return CustomRecordSchema(
        record_type="ingredients",
        fields=[
            {"name": "item", "type": "string"},
            {"name": "quantity", "type": "number"},
            {"name": "optional", "type": "boolean"},
            {"name": "added_on", "type": "date"},
            {"name": "notes", "type": "string_list"},
        ],
    )


def test_record_type_slug_is_normalized() -> None:
    schema = CustomRecordSchema(
        record_type=" Recipe-Steps ",
        fields=[{"name": "step", "type": "string"}],
    )
    assert schema.record_type == "recipe_steps"
    assert schema.label == "Recipe steps"


def test_invalid_record_type_rejected() -> None:
    with pytest.raises(ValidationError, match="Record type"):
        CustomRecordSchema(record_type="9bad!", fields=[{"name": "step"}])


def test_empty_field_list_rejected() -> None:
    with pytest.raises(ValidationError):
        CustomRecordSchema(record_type="ingredients", fields=[])


def test_duplicate_field_names_rejected() -> None:
    with pytest.raises(ValidationError, match="Duplicate field name"):
        CustomRecordSchema(
            record_type="ingredients",
            fields=[{"name": "item"}, {"name": "Item"}],
        )


def test_reserved_field_name_rejected() -> None:
    with pytest.raises(ValidationError, match="reserved"):
        CustomFieldSpec(name="mentions")


def test_field_label_defaults_from_name() -> None:
    spec = CustomFieldSpec(name="pub_date", type="date")
    assert spec.label == "Pub date"


def test_record_model_coerces_value_types() -> None:
    model = build_record_fields_model(_ingredients_schema().fields)
    record = model.model_validate(
        {
            "item": "flour",
            "quantity": "2,000",
            "optional": "yes",
            "added_on": "2026-06-10T12:00:00Z",
            "notes": "sifted",
        }
    )
    payload = record.model_dump()
    assert payload["quantity"] == 2000.0
    assert payload["optional"] is True
    assert payload["added_on"] == "2026-06-10"
    assert payload["notes"] == ["sifted"]


def test_record_model_rejects_unparseable_number() -> None:
    model = build_record_fields_model(_ingredients_schema().fields)
    with pytest.raises(ValidationError):
        model.model_validate({"item": "flour", "quantity": "a pinch"})


def test_record_model_rejects_bad_date() -> None:
    model = build_record_fields_model(_ingredients_schema().fields)
    with pytest.raises(ValidationError):
        model.model_validate({"item": "flour", "added_on": "next Tuesday"})


def test_record_model_rejects_record_with_no_populated_fields() -> None:
    model = build_record_fields_model(_ingredients_schema().fields)
    with pytest.raises(ValidationError, match="at least one populated field"):
        model.model_validate({"item": None, "quantity": None})


def test_record_model_ignores_undeclared_keys() -> None:
    model = build_record_fields_model(_ingredients_schema().fields)
    record = model.model_validate({"item": "flour", "surprise": "ignored"})
    assert "surprise" not in record.model_dump()
