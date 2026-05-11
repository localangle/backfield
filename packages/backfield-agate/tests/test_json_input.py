"""JSONInput and shared document normalization."""

from backfield_agate.nodes.json_input import (
    json_input_output_from_dict,
    resolve_document_body_text,
    run_json_input,
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
