"""Decision and embedding rows stay off language-model lists unless requested."""

from __future__ import annotations

from backfield_ai.catalog_visibility import (
    include_in_language_model_list,
    matches_capability_request,
)


def test_language_lists_hide_decision_and_embedding_rows() -> None:
    assert include_in_language_model_list(
        model_kind="generative",
        capabilities=["text", "json"],
    )
    assert include_in_language_model_list(model_kind="chat", capabilities=["text"])
    assert not include_in_language_model_list(
        model_kind="decision",
        capabilities=["decision"],
    )
    assert not include_in_language_model_list(
        model_kind="decision",
        capabilities=["text", "json"],
    )
    assert not include_in_language_model_list(
        model_kind="embedding",
        capabilities=["embedding"],
    )
    assert not include_in_language_model_list(model_kind="embedding", capabilities=[])


def test_capability_filter_returns_specialized_kinds_only_when_asked() -> None:
    decision = {"model_kind": "decision", "capabilities": ["decision"]}
    embedding = {"model_kind": "embedding", "capabilities": ["embedding"]}
    generative = {"model_kind": "generative", "capabilities": ["text", "json"]}

    assert matches_capability_request(**decision, requested=set())
    assert not matches_capability_request(**decision, requested={"text", "json"})
    assert not matches_capability_request(**decision, requested={"embedding"})
    assert matches_capability_request(**decision, requested={"decision"})

    assert not matches_capability_request(**embedding, requested={"text"})
    assert matches_capability_request(**embedding, requested={"embedding"})

    assert matches_capability_request(**generative, requested={"text", "json"})
    assert not matches_capability_request(**generative, requested={"decision"})
    assert not matches_capability_request(**generative, requested={"embedding"})
