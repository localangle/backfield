"""Processed-item article metadata review rows."""

from __future__ import annotations

from backfield_entities.ingest.article_metadata.processed_item import (
    build_processed_item_article_meta_rows,
    collect_article_metadata_blocks_from_output,
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
