"""Tests for processed-item article metadata merge helpers."""

from __future__ import annotations

from backfield_entities.ingest.article_metadata.processed_item import (
    apply_merged_article_meta_to_output,
    article_meta_overlay_has_content,
    article_meta_review_rows_from_overlay,
    merge_article_meta_with_overlay,
    normalize_article_meta_overlay,
)


def test_normalize_article_meta_overlay_reads_category_patches() -> None:
    overlay = {
        "article_meta": {
            "by_id": {
                "7": {"category": "Politics", "meta_type": "subject"},
            }
        }
    }
    assert normalize_article_meta_overlay(overlay) == {
        "7": {"category": "Politics", "meta_type": "subject"},
    }
    assert article_meta_overlay_has_content(overlay) is True


def test_merge_article_meta_with_overlay_updates_category_and_source() -> None:
    rows = [
        {
            "id": 7,
            "meta_type": "subject",
            "category": "local_government_politics",
            "rationale": "Because",
            "confidence": 0.8,
            "prompt_preset": "subject",
            "source": "model",
        }
    ]
    merged = merge_article_meta_with_overlay(
        rows,
        {"7": {"category": "Politics", "meta_type": "subject"}},
    )
    assert merged[0]["category"] == "Politics"
    assert merged[0]["source"] == "review"


def test_apply_merged_article_meta_to_output_patches_matching_meta_type() -> None:
    output = {
        "stylebook_output": {
            "article_metadata": {
                "meta_type": "subject",
                "category": "local_government_politics",
                "rationale": "Because",
                "confidence": 0.8,
            }
        }
    }
    apply_merged_article_meta_to_output(
        output,
        [{"meta_type": "subject", "category": "Politics"}],
    )
    assert output["stylebook_output"]["article_metadata"]["category"] == "Politics"


def test_article_meta_review_rows_from_overlay() -> None:
    rows = article_meta_review_rows_from_overlay(
        {
            "article_meta": {
                "by_id": {
                    "3": {"category": "Sports", "meta_type": "subject"},
                }
            }
        }
    )
    assert rows == [{"meta_type": "subject", "category": "Sports"}]
