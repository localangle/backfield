"""Tests for custom Article Metadata preset meta_type handling."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from agate_nodes.article_metadata.presets import (
    normalize_custom_meta_type,
    resolve_meta_type,
)
from agate_runtime.context import AgateEnvContext
from agate_runtime.runners import run_article_metadata_runtime


def test_normalize_custom_meta_type_accepts_slug() -> None:
    assert normalize_custom_meta_type("new_category") == "new_category"
    assert normalize_custom_meta_type(" New-Category ") == "new_category"


def test_normalize_custom_meta_type_rejects_empty() -> None:
    with pytest.raises(ValueError, match="requires a metadata type"):
        normalize_custom_meta_type("")


def test_normalize_custom_meta_type_rejects_reserved_preset_name() -> None:
    with pytest.raises(ValueError, match="reserved"):
        normalize_custom_meta_type("subject")


def test_resolve_meta_type_uses_bundled_preset_id() -> None:
    assert resolve_meta_type("format", custom_meta_type="ignored") == "format"


def test_run_custom_preset_emits_user_meta_type() -> None:
    prompt = (
        "Classify this dimension.\n\n"
        "## Categories\n"
        "- category_a\n"
        "- category_b\n"
        "- other\n\n"
        "## Article text\n\n"
        "{text}"
    )
    llm_payload = {
        "category": "category_a",
        "rationale": "Best fit for the article.",
        "confidence": 0.91,
    }

    with patch(
        "agate_nodes.article_metadata.node_port.call_llm",
        return_value=json.dumps(llm_payload),
    ):
        out = run_article_metadata_runtime(
            {
                "prompt_preset": "custom",
                "meta_type": "new_category",
                "prompt": prompt,
            },
            {"text": "Local bakery opens on Main Street."},
            AgateEnvContext(run_id="run-test"),
        )

    assert out["article_metadata"] == {
        "meta_type": "new_category",
        "category": "category_a",
        "rationale": "Best fit for the article.",
        "confidence": 0.91,
        "prompt_preset": "custom",
    }


def test_run_custom_preset_requires_meta_type() -> None:
    with patch(
        "agate_nodes.article_metadata.node_port.call_llm",
        return_value=json.dumps(
            {"category": "safe", "rationale": "ok", "confidence": 0.5}
        ),
    ):
        with pytest.raises(ValueError, match="requires a metadata type"):
            run_article_metadata_runtime(
                {
                    "prompt_preset": "custom",
                    "meta_type": "",
                    "prompt": "## Categories\n- safe\n\n{text}",
                },
                {"text": "Story body."},
                AgateEnvContext(run_id="run-test"),
            )
