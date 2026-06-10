"""Tests for Article Metadata node runtime."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from agate_runtime.context import AgateEnvContext
from agate_runtime.runners import run_article_metadata_runtime


def test_run_emits_article_metadata_with_passthrough_fields() -> None:
    llm_payload = {
        "category": "Local news",
        "rationale": "Neighborhood council coverage.",
        "confidence": 0.77,
    }

    with patch(
        "agate_nodes.article_metadata.node_port.call_llm",
        return_value=json.dumps(llm_payload),
    ):
        out = run_article_metadata_runtime(
            {"prompt_preset": "topic"},
            {"text": "Story body.", "headline": "Council vote", "url": "https://example.com"},
            AgateEnvContext(run_id="run-test"),
        )

    assert out["text"] == "Story body."
    assert out["headline"] == "Council vote"
    assert out["url"] == "https://example.com"
    assert out["article_metadata"] == {
        "meta_type": "topic",
        "category": "Local news",
        "rationale": "Neighborhood council coverage.",
        "confidence": 0.77,
        "prompt_preset": "topic",
    }


def test_run_rejects_invalid_category_from_llm() -> None:
    llm_payload = {
        "category": "Weather",
        "rationale": "Not in list.",
        "confidence": 0.5,
    }

    with patch(
        "agate_nodes.article_metadata.node_port.call_llm",
        return_value=json.dumps(llm_payload),
    ):
        with pytest.raises(ValueError, match="not allowed"):
            run_article_metadata_runtime(
                {"prompt_preset": "topic"},
                {"text": "Story body."},
                AgateEnvContext(run_id="run-test"),
            )
