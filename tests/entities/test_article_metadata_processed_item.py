"""Processed-item article metadata review rows."""

from __future__ import annotations

from backfield_entities.ingest.article_metadata.processed_item import (
    apply_merged_article_meta_rows_to_output,
    build_processed_item_article_meta_rows,
    collect_article_metadata_blocks_from_output,
    find_article_meta_row_by_id,
    merge_article_meta_with_overlay,
    remove_article_meta_from_output,
)


def test_collect_article_metadata_blocks_from_output_dedupes_nodes() -> None:
    output = {
        "article_metadata": {
            "article_metadata": {
                "meta_type": "subject",
                "category": "public_safety_crime",
                "rationale": "Crime story.",
                "confidence": 0.82,
            }
        },
        "article_metadata_node-18": {
            "article_metadata": {
                "meta_type": "format",
                "category": "news_story",
                "rationale": "News report.",
                "confidence": 0.78,
            }
        },
    }
    blocks = collect_article_metadata_blocks_from_output(output)
    assert {block["meta_type"] for block in blocks} == {"subject", "format"}


def test_collect_article_metadata_blocks_from_json_output_consolidated() -> None:
    output = {
        "json_output": {
            "consolidated": {
                "headline": "Story",
                "article_metadata": {
                    "meta_type": "subject",
                    "category": "local_news",
                    "rationale": "Because",
                    "confidence": 0.82,
                },
            }
        }
    }
    blocks = collect_article_metadata_blocks_from_output(output)
    assert len(blocks) == 1
    assert blocks[0]["meta_type"] == "subject"


def test_build_processed_item_article_meta_rows_falls_back_to_output() -> None:
    rows = build_processed_item_article_meta_rows(
        None,
        article_id=None,
        overlay=None,
        output={
            "article_metadata": {
                "article_metadata": {
                    "meta_type": "subject",
                    "category": "public_safety_crime",
                    "rationale": "Crime story.",
                    "confidence": 0.82,
                    "prompt_preset": "subject",
                }
            },
            "article_metadata_node-18": {
                "article_metadata": {
                    "meta_type": "user_need",
                    "category": "update_me",
                    "rationale": "Breaking update.",
                    "confidence": 0.72,
                }
            },
        },
    )
    assert len(rows) == 2
    assert all(row["id"] < 0 for row in rows)
    assert {row["meta_type"] for row in rows} == {"subject", "user_need"}


def test_find_article_meta_row_by_id_resolves_synthetic_row() -> None:
    output = {
        "json_output": {
            "consolidated": {
                "article_metadata": {
                    "meta_type": "subject",
                    "category": "local_news",
                    "rationale": "Because",
                    "confidence": 0.82,
                }
            }
        }
    }
    rows = build_processed_item_article_meta_rows(
        None,
        article_id=None,
        overlay=None,
        output=output,
    )
    assert len(rows) == 1
    row_id = rows[0]["id"]
    found = find_article_meta_row_by_id(
        None,
        article_id=None,
        output=output,
        overlay=None,
        meta_row_id=row_id,
    )
    assert found is not None
    assert found["meta_type"] == "subject"


def test_merge_article_meta_with_overlay_filters_removed_ids() -> None:
    rows = [
        {
            "id": 1,
            "meta_type": "subject",
            "category": "local_news",
            "rationale": "Because",
            "confidence": 0.82,
            "source": "model",
        },
        {
            "id": 2,
            "meta_type": "format",
            "category": "news_story",
            "rationale": "Because",
            "confidence": 0.72,
            "source": "model",
        },
    ]
    merged = merge_article_meta_with_overlay(rows, {}, removed_ids={"2"})
    assert [row["id"] for row in merged] == [1]


def test_remove_article_meta_from_output_json_output_consolidated() -> None:
    output = {
        "json_output": {
            "consolidated": {
                "headline": "Story",
                "article_metadata": {
                    "meta_type": "subject",
                    "category": "local_news",
                    "rationale": "Because",
                    "confidence": 0.82,
                },
            }
        }
    }
    rows = build_processed_item_article_meta_rows(
        None,
        article_id=None,
        overlay=None,
        output=output,
    )
    remove_article_meta_from_output(output, removed_row_ids={rows[0]["id"]})
    assert "article_metadata" not in output["json_output"]["consolidated"]
    assert build_processed_item_article_meta_rows(
        None,
        article_id=None,
        overlay={"article_meta": {"removed_ids": [str(rows[0]["id"])]}},
        output=output,
    ) == []


def test_build_processed_item_article_meta_rows_includes_user_added() -> None:
    overlay = {
        "article_meta": {
            "user_added": [
                {
                    "id": -900001,
                    "meta_type": "format",
                    "category": "news_story",
                    "rationale": "Added during review.",
                    "confidence": 1.0,
                    "prompt_preset": "format",
                }
            ]
        }
    }
    rows = build_processed_item_article_meta_rows(
        None,
        article_id=None,
        overlay=overlay,
        output={"json_output": {"consolidated": {"headline": "Story"}}},
    )
    assert len(rows) == 1
    assert rows[0]["meta_type"] == "format"
    assert rows[0]["source"] == "review"


def test_apply_merged_article_meta_rows_to_output_inserts_new_block() -> None:
    output = {
        "json_output": {
            "consolidated": {
                "headline": "Story",
            }
        }
    }
    apply_merged_article_meta_rows_to_output(
        output,
        [
            {
                "meta_type": "subject",
                "category": "local_news",
                "rationale": "Added during review.",
                "confidence": 1.0,
                "prompt_preset": "subject",
            }
        ],
    )
    block = output["json_output"]["consolidated"]["article_metadata"]
    assert block["meta_type"] == "subject"
    assert block["category"] == "local_news"
