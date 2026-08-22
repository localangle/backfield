"""JSONInput and shared document normalization."""

import pytest
from agate_runtime.nodes.json_input import (
    documents_for_batch_execution,
    is_json_input_multi_document,
    json_input_output_from_dict,
    parse_documents_entries,
    resolve_document_body_text,
    run_json_input,
    single_document_from_params,
)


def test_json_input_output_from_dict_matches_run_json_input():
    params = {
        "text": "  body  ",
        "headline": "A story",
        "url": "https://example.com/x",
        "onChange": "strip-me",
    }
    a = run_json_input(params, {})
    b = json_input_output_from_dict(params)
    assert a == b
    assert a["text"] == "body"
    assert a["headline"] == "A story"
    assert a["url"] == "https://example.com/x"
    assert "onChange" not in a


def test_resolve_document_body_text_prefers_longer_field_over_short_text_label() -> None:
    doc = {
        "text": "Music",
        "article_text": "The festival runs all weekend in Grant Park with Chicago-area headliners.",
        "headline": "Events",
    }
    assert resolve_document_body_text(doc) == doc["article_text"]
    out = json_input_output_from_dict(doc)
    assert out["text"] == doc["article_text"]
    assert out["headline"] == "Events"


def test_is_json_input_multi_document() -> None:
    assert is_json_input_multi_document({"text": "a"}) is False
    assert (
        is_json_input_multi_document(
            {
                "documents": [
                    {"text": "a", "source_file": "a.json"},
                    {"text": "b", "source_file": "b.json"},
                ]
            }
        )
        is True
    )


def test_parse_documents_entries_and_batch_normalize() -> None:
    params = {
        "public_alias": "ingress",
        "documents": [
            {"source_file": "a.json", "text": " First ", "headline": "A"},
            {"source_file": "b.json", "article_text": "Second body", "text": "x"},
        ],
    }
    entries = parse_documents_entries(params)
    assert len(entries) == 2
    assert entries[0][0] == "a.json"
    batch = documents_for_batch_execution(params)
    assert batch[0][1]["text"] == "First"
    assert batch[0][1]["headline"] == "A"
    assert batch[0][1]["source_file"] == "a.json"
    assert batch[1][1]["text"] == "Second body"


def test_parse_documents_rejects_over_cap() -> None:
    docs = [{"text": f"body {i}", "source_file": f"{i}.json"} for i in range(21)]
    with pytest.raises(ValueError, match="at most 20"):
        parse_documents_entries({"documents": docs})


def test_single_document_from_flat_and_length_one_list() -> None:
    flat, source = single_document_from_params({"text": "hi", "public_alias": "x"})
    assert flat["text"] == "hi"
    assert flat["public_alias"] == "x"
    assert source == "inline:json"

    one, source_one = single_document_from_params(
        {"documents": [{"source_file": "only.json", "text": "solo"}]}
    )
    assert one["text"] == "solo"
    assert source_one == "only.json"

    with pytest.raises(ValueError, match="batch setup"):
        single_document_from_params(
            {
                "documents": [
                    {"text": "a", "source_file": "a.json"},
                    {"text": "b", "source_file": "b.json"},
                ]
            }
        )
