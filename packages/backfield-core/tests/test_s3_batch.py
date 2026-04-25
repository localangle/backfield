"""Unit tests for S3 batch helpers."""

from __future__ import annotations

import json

import pytest
from backfield_core.s3_batch import (
    graph_spec_json_contains_s3_input,
    parse_s3_text_json_document,
    s3_max_files_from_params,
)


def test_parse_s3_text_json_document_accepts_valid() -> None:
    doc, err = parse_s3_text_json_document(json.dumps({"text": " Hello ", "x": 1}))
    assert err is None
    assert doc == {"text": " Hello ", "x": 1}


@pytest.mark.parametrize(
    "raw,reason_substr",
    [
        ("not json", "invalid_json"),
        ("[]", "json_not_object"),
        ("{}", "missing_or_empty_text"),
        ('{"text":""}', "missing_or_empty_text"),
    ],
)
def test_parse_s3_text_json_document_rejects(raw: str, reason_substr: str) -> None:
    doc, err = parse_s3_text_json_document(raw)
    assert doc is None
    assert err is not None
    assert reason_substr in err


def test_s3_max_files_from_params() -> None:
    assert s3_max_files_from_params({}) == 500
    assert s3_max_files_from_params({"max_files": "3"}) == 3
    assert s3_max_files_from_params({"max_files": 0}) == 1
    assert s3_max_files_from_params({"max_files": 999999}) == 10_000


def test_graph_spec_json_contains_s3_input() -> None:
    spec = json.dumps(
        {
            "name": "g",
            "nodes": [
                {"id": "a", "type": "TextInput", "params": {}},
                {"id": "b", "type": "S3Input", "params": {}},
            ],
            "edges": [],
        }
    )
    assert graph_spec_json_contains_s3_input(spec) is True
    empty = json.dumps({"name": "g", "nodes": [], "edges": []})
    assert graph_spec_json_contains_s3_input(empty) is False
