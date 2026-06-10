"""Tests for Article Metadata node runtime."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from agate_runtime.context import AgateEnvContext
from agate_runtime.runners import run_article_metadata_runtime


def test_run_emits_article_metadata_with_passthrough_fields() -> None:
    llm_payload = {
        "category": "update_me",
        "rationale": "Timely reporting on a council vote.",
        "confidence": 0.77,
    }

    with patch(
        "agate_nodes.article_metadata.node_port.call_llm",
        return_value=json.dumps(llm_payload),
    ):
        out = run_article_metadata_runtime(
            {"prompt_preset": "user_need"},
            {"text": "Story body.", "headline": "Council vote", "url": "https://example.com"},
            AgateEnvContext(run_id="run-test"),
        )

    assert out["text"] == "Story body."
    assert out["headline"] == "Council vote"
    assert out["url"] == "https://example.com"
    assert out["article_metadata"] == {
        "meta_type": "user_need",
        "category": "update_me",
        "rationale": "Timely reporting on a council vote.",
        "confidence": 0.77,
        "prompt_preset": "user_need",
    }


def test_run_emits_timeframe_category_for_temporal_orientation_preset() -> None:
    llm_payload = {
        "category": "future",
        "rationale": "The story is oriented toward an upcoming vote.",
        "confidence": 0.91,
    }

    with patch(
        "agate_nodes.article_metadata.node_port.call_llm",
        return_value=json.dumps(llm_payload),
    ):
        out = run_article_metadata_runtime(
            {"prompt_preset": "temporal_orientation"},
            {"text": "Council will vote next week on the zoning plan."},
            AgateEnvContext(run_id="run-test"),
        )

    assert out["article_metadata"] == {
        "meta_type": "temporal_orientation",
        "category": "future",
        "rationale": "The story is oriented toward an upcoming vote.",
        "confidence": 0.91,
        "prompt_preset": "temporal_orientation",
    }


def test_run_emits_user_need_for_user_need_preset() -> None:
    llm_payload = {
        "category": "update_me",
        "rationale": "Timely information about a local government decision.",
        "confidence": 0.95,
    }

    with patch(
        "agate_nodes.article_metadata.node_port.call_llm",
        return_value=json.dumps(llm_payload),
    ):
        out = run_article_metadata_runtime(
            {"prompt_preset": "user_need"},
            {"text": "City council approves budget after 5-2 vote."},
            AgateEnvContext(run_id="run-test"),
        )

    assert out["article_metadata"] == {
        "meta_type": "user_need",
        "category": "update_me",
        "rationale": "Timely information about a local government decision.",
        "confidence": 0.95,
        "prompt_preset": "user_need",
    }


def test_run_emits_needs_for_information_needs_preset() -> None:
    llm_payload = [
        {
            "category": "education",
            "rationale": "School access is central.",
            "confidence": 0.94,
        },
        {
            "category": "political_information",
            "rationale": "Board vote with policy implications.",
            "confidence": 0.82,
        },
    ]

    with patch(
        "agate_nodes.article_metadata.node_port.call_llm",
        return_value=json.dumps(llm_payload),
    ):
        out = run_article_metadata_runtime(
            {"prompt_preset": "information_needs"},
            {"text": "School board votes to close two elementary schools next year."},
            AgateEnvContext(run_id="run-test"),
        )

    meta = out["article_metadata"]
    assert meta["meta_type"] == "information_needs"
    assert meta["category"] == "education"
    assert len(meta["needs"]) == 2
    assert meta["needs"][0]["category"] == "education"


def test_run_emits_scope_for_geographic_scope_preset() -> None:
    llm_payload = {
        "category": "city_municipality",
        "rationale": "The proposed budget affects residents across the entire city.",
        "confidence": 0.93,
    }

    with patch(
        "agate_nodes.article_metadata.node_port.call_llm",
        return_value=json.dumps(llm_payload),
    ):
        out = run_article_metadata_runtime(
            {"prompt_preset": "geographic_scope"},
            {"text": "Mayor proposes budget with expanded youth programs."},
            AgateEnvContext(run_id="run-test"),
        )

    assert out["article_metadata"] == {
        "meta_type": "geographic_scope",
        "category": "city_municipality",
        "rationale": "The proposed budget affects residents across the entire city.",
        "confidence": 0.93,
        "prompt_preset": "geographic_scope",
    }


def test_run_emits_subjects_for_subject_preset() -> None:
    llm_payload = [
        {
            "category": "local_government_politics",
            "rationale": "Council vote is central.",
            "confidence": 0.92,
        },
        {
            "category": "housing_affordability_homelessness",
            "rationale": "Affordable housing is a major theme.",
            "confidence": 0.86,
        },
    ]

    with patch(
        "agate_nodes.article_metadata.node_port.call_llm",
        return_value=json.dumps(llm_payload),
    ):
        out = run_article_metadata_runtime(
            {"prompt_preset": "subject"},
            {"text": "Council vote on zoning sparks affordable housing debate."},
            AgateEnvContext(run_id="run-test"),
        )

    meta = out["article_metadata"]
    assert meta["meta_type"] == "subject"
    assert meta["category"] == "local_government_politics"
    assert len(meta["subjects"]) == 2
    assert meta["subjects"][0]["category"] == "local_government_politics"


def test_run_emits_format_category_for_format_preset() -> None:
    llm_payload = {
        "category": "news_story",
        "rationale": "Straightforward reporting on a council vote.",
        "confidence": 0.95,
    }

    with patch(
        "agate_nodes.article_metadata.node_port.call_llm",
        return_value=json.dumps(llm_payload),
    ):
        out = run_article_metadata_runtime(
            {"prompt_preset": "format"},
            {"text": "City council approves budget after 5-2 vote."},
            AgateEnvContext(run_id="run-test"),
        )

    assert out["article_metadata"] == {
        "meta_type": "format",
        "category": "news_story",
        "rationale": "Straightforward reporting on a council vote.",
        "confidence": 0.95,
        "prompt_preset": "format",
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
                {"prompt_preset": "format"},
                {"text": "Story body."},
                AgateEnvContext(run_id="run-test"),
            )
