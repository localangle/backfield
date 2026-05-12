"""Unit tests for S3 batch helpers."""

from __future__ import annotations

import json

import pytest
from agate_runtime.s3_batch import (
    graph_spec_json_contains_s3_input,
    parse_s3_text_json_document,
    s3_max_files_from_params,
)


def test_parse_s3_text_json_document_accepts_valid() -> None:
    doc, err = parse_s3_text_json_document(json.dumps({"text": " Hello ", "x": 1}))
    assert err is None
    assert doc == {"text": "Hello", "x": 1}


def test_parse_s3_text_json_document_accepts_article_text_when_text_empty() -> None:
    raw = json.dumps(
        {
            "text": "",
            "article_text": "Full narrative here.",
            "headline": "Hi",
        }
    )
    doc, err = parse_s3_text_json_document(raw)
    assert err is None
    assert doc is not None
    assert doc["text"] == "Full narrative here."


def test_parse_s3_text_json_document_prefers_longest_body_field() -> None:
    doc, err = parse_s3_text_json_document(
        json.dumps({"text": "Music", "article_text": "Something longer than Music."})
    )
    assert err is None
    assert doc is not None
    assert doc["text"] == "Something longer than Music."


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
