"""Tests for Custom Extract LLM response parsing and mention grounding."""

from __future__ import annotations

import json

import pytest
from agate_nodes.custom_extract.parse import parse_custom_extract_response
from agate_nodes.custom_extract.schema import CustomRecordSchema


def _schema() -> CustomRecordSchema:
    return CustomRecordSchema(
        record_type="ingredients",
        fields=[
            {"name": "item", "type": "string"},
            {"name": "quantity", "type": "string"},
        ],
    )


def _grounded_record(item: str = "flour", quantity: str = "2 cups") -> dict:
    return {
        "fields": {"item": item, "quantity": quantity},
        "mentions": [{"text": f"{quantity} of {item}", "quote": False}],
        "confidence": 0.9,
    }


def test_parse_happy_path() -> None:
    result = parse_custom_extract_response(
        {"records": [_grounded_record()]},
        record_schema=_schema(),
    )
    assert result.dropped_ungrounded == 0
    assert len(result.records) == 1
    record = result.records[0]
    assert record.fields == {"item": "flour", "quantity": "2 cups"}
    assert record.mentions[0].text == "2 cups of flour"
    assert record.confidence == 0.9
    assert record.key


def test_record_keys_are_stable_and_unique() -> None:
    payload = {
        "records": [
            _grounded_record(),
            _grounded_record(),
            _grounded_record("salt", "1 tsp"),
        ]
    }
    first = parse_custom_extract_response(payload, record_schema=_schema())
    second = parse_custom_extract_response(payload, record_schema=_schema())
    assert [r.key for r in first.records] == [r.key for r in second.records]
    assert len({r.key for r in first.records}) == 3


def test_ungrounded_records_are_dropped_with_count() -> None:
    ungrounded = {"fields": {"item": "unicorn dust", "quantity": "1 oz"}, "mentions": []}
    result = parse_custom_extract_response(
        {"records": [_grounded_record(), ungrounded]},
        record_schema=_schema(),
    )
    assert len(result.records) == 1
    assert result.dropped_ungrounded == 1


def test_empty_records_array_is_valid() -> None:
    result = parse_custom_extract_response({"records": []}, record_schema=_schema())
    assert result.records == []
    assert result.dropped_ungrounded == 0


def test_missing_records_key_raises() -> None:
    with pytest.raises(ValueError, match='"records"'):
        parse_custom_extract_response({"items": []}, record_schema=_schema())


def test_schema_violation_raises_clear_error() -> None:
    bad = {
        "fields": {"item": None, "quantity": None},
        "mentions": [{"text": "snippet"}],
    }
    with pytest.raises(ValueError, match="does not match the declared fields"):
        parse_custom_extract_response({"records": [bad]}, record_schema=_schema())


def test_flat_records_without_fields_wrapper_are_tolerated() -> None:
    flat = {
        "item": "flour",
        "quantity": "2 cups",
        "mentions": [{"text": "2 cups of flour"}],
    }
    result = parse_custom_extract_response({"records": [flat]}, record_schema=_schema())
    assert result.records[0].fields == {"item": "flour", "quantity": "2 cups"}


def test_json_string_payload_is_decoded() -> None:
    payload = json.dumps({"records": [_grounded_record()]})
    result = parse_custom_extract_response(payload, record_schema=_schema())
    assert len(result.records) == 1


def test_string_mentions_are_coerced() -> None:
    record = {
        "fields": {"item": "flour", "quantity": "2 cups"},
        "mentions": ["2 cups of flour"],
    }
    result = parse_custom_extract_response({"records": [record]}, record_schema=_schema())
    assert result.records[0].mentions[0].text == "2 cups of flour"
    assert result.records[0].mentions[0].quote is False


def test_llm_quote_flag_is_stripped_to_mention_only() -> None:
    record = {
        "fields": {"item": "flour", "quantity": "2 cups"},
        "mentions": [{"text": '"Mix well," she said.', "quote": True}],
    }
    result = parse_custom_extract_response({"records": [record]}, record_schema=_schema())
    assert result.records[0].mentions[0].quote is False


def test_out_of_range_confidence_raises() -> None:
    record = _grounded_record()
    record["confidence"] = 1.5
    with pytest.raises(ValueError, match="confidence"):
        parse_custom_extract_response({"records": [record]}, record_schema=_schema())
