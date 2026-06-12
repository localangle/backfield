"""Tests for ``api.processed_item.custom_records_merge``."""

from __future__ import annotations

from api.processed_item.custom_records_merge import (
    apply_custom_records_overlay_to_output,
    custom_records_overlay_has_content,
    merge_custom_records_block,
    normalize_custom_records_overlay,
    reviewed_custom_records_block,
)


def _ingredients_set(records: list[dict] | None = None) -> dict:
    return {
        "label": "Ingredients",
        "schema": [
            {"name": "name", "label": "Name", "type": "string"},
            {"name": "quantity", "label": "Quantity", "type": "string"},
        ],
        "records": records
        if records is not None
        else [
            {
                "key": "abc123",
                "fields": {"name": "Flour", "quantity": "2 cups"},
                "mentions": [{"text": "two cups of flour", "quote": False}],
                "confidence": 0.9,
            },
            {
                "key": "def456",
                "fields": {"name": "Salt", "quantity": "1 tsp"},
                "mentions": [{"text": "a teaspoon of salt", "quote": False}],
                "confidence": 0.8,
            },
        ],
        "dropped_ungrounded": 0,
    }


class TestNormalizeCustomRecordsOverlay:
    def test_empty_overlays_have_no_content(self) -> None:
        assert normalize_custom_records_overlay(None) == {}
        assert normalize_custom_records_overlay({}) == {}
        assert normalize_custom_records_overlay({"custom_records": {}}) == {}
        assert not custom_records_overlay_has_content({"custom_records": {"ingredients": {}}})

    def test_field_patch_is_content(self) -> None:
        overlay = {
            "custom_records": {
                "ingredients": {"by_key": {"abc123": {"fields": {"quantity": "3 cups"}}}}
            }
        }
        normalized = normalize_custom_records_overlay(overlay)
        assert custom_records_overlay_has_content(overlay)
        assert normalized["ingredients"].by_key == {"abc123": {"fields": {"quantity": "3 cups"}}}

    def test_removed_keys_and_user_added_are_content(self) -> None:
        assert custom_records_overlay_has_content(
            {"custom_records": {"ingredients": {"removed_keys": ["abc123"]}}}
        )
        assert custom_records_overlay_has_content(
            {
                "custom_records": {
                    "ingredients": {
                        "user_added": [
                            {"key": "user_record:1", "fields": {"name": "Sugar"}}
                        ]
                    }
                }
            }
        )

    def test_malformed_entries_are_ignored(self) -> None:
        overlay = {
            "custom_records": {
                "ingredients": {
                    "by_key": {"": {"fields": {}}, "ok": "not-a-dict"},
                    "user_added": [
                        "bogus",
                        {"fields": {"name": "No key"}},
                        {"key": "user_record:1", "fields": {}},
                    ],
                    "removed_keys": [42, ""],
                }
            }
        }
        assert normalize_custom_records_overlay(overlay) == {}


class TestMergeCustomRecordsBlock:
    def test_field_patch_merges_into_record(self) -> None:
        overlay = {
            "custom_records": {
                "ingredients": {"by_key": {"abc123": {"fields": {"quantity": "3 cups"}}}}
            }
        }
        merged = merge_custom_records_block({"ingredients": _ingredients_set()}, overlay)
        records = merged["ingredients"]["records"]
        assert records[0]["fields"] == {"name": "Flour", "quantity": "3 cups"}
        assert records[0]["mentions"] == [{"text": "two cups of flour", "quote": False}]
        assert records[1]["fields"]["name"] == "Salt"

    def test_mentions_patch_replaces_mention_list(self) -> None:
        overlay = {
            "custom_records": {
                "ingredients": {
                    "by_key": {"abc123": {"mentions": [{"text": "flour", "quote": False}]}}
                }
            }
        }
        merged = merge_custom_records_block({"ingredients": _ingredients_set()}, overlay)
        assert merged["ingredients"]["records"][0]["mentions"] == [
            {"text": "flour", "quote": False}
        ]

    def test_removed_key_drops_record(self) -> None:
        overlay = {"custom_records": {"ingredients": {"removed_keys": ["abc123"]}}}
        merged = merge_custom_records_block({"ingredients": _ingredients_set()}, overlay)
        keys = [record["key"] for record in merged["ingredients"]["records"]]
        assert keys == ["def456"]

    def test_user_added_record_carries_review_source(self) -> None:
        overlay = {
            "custom_records": {
                "ingredients": {
                    "user_added": [
                        {"key": "user_record:1", "fields": {"name": "Sugar", "quantity": "1 cup"}}
                    ]
                }
            }
        }
        merged = merge_custom_records_block({"ingredients": _ingredients_set()}, overlay)
        records = merged["ingredients"]["records"]
        assert len(records) == 3
        added = records[-1]
        assert added["key"] == "user_record:1"
        assert added["source"] == "review"
        assert added["mentions"] == []

    def test_user_added_record_may_carry_mentions(self) -> None:
        overlay = {
            "custom_records": {
                "ingredients": {
                    "user_added": [
                        {
                            "key": "user_record:1",
                            "fields": {"name": "Sugar"},
                            "mentions": [{"text": "a cup of sugar", "quote": True}],
                        }
                    ]
                }
            }
        }
        merged = merge_custom_records_block({"ingredients": _ingredients_set()}, overlay)
        added = merged["ingredients"]["records"][-1]
        assert added["mentions"] == [{"text": "a cup of sugar", "quote": False}]

    def test_sibling_record_types_untouched(self) -> None:
        overlay = {"custom_records": {"ingredients": {"removed_keys": ["abc123"]}}}
        steps_set = {
            "label": "Steps",
            "schema": [{"name": "description", "label": "Description", "type": "string"}],
            "records": [
                {
                    "key": "s1",
                    "fields": {"description": "Preheat oven"},
                    "mentions": [{"text": "Preheat the oven", "quote": False}],
                }
            ],
            "dropped_ungrounded": 0,
        }
        merged = merge_custom_records_block(
            {"ingredients": _ingredients_set(), "steps": steps_set}, overlay
        )
        assert merged["steps"] == steps_set

    def test_no_overlay_returns_equal_block(self) -> None:
        block = {"ingredients": _ingredients_set()}
        assert merge_custom_records_block(block, None) == block
        assert merge_custom_records_block(block, {}) == block


class TestReviewedCustomRecordsBlock:
    def test_unions_node_and_consolidated_blocks_and_applies_overlay(self) -> None:
        output = {
            "custom_extract": {"custom_records": {"ingredients": _ingredients_set()}},
            "db_output": {
                "consolidated": {"custom_records": {"ingredients": _ingredients_set()}}
            },
        }
        overlay = {"custom_records": {"ingredients": {"removed_keys": ["abc123"]}}}
        merged = reviewed_custom_records_block(output, overlay)
        keys = [record["key"] for record in merged["ingredients"]["records"]]
        assert keys == ["def456"]

    def test_empty_output_returns_user_added_only_types_nothing(self) -> None:
        overlay = {
            "custom_records": {
                "ingredients": {
                    "user_added": [{"key": "user_record:1", "fields": {"name": "Sugar"}}]
                }
            }
        }
        # No model block for the record type: nothing to merge into, so no set is produced.
        assert reviewed_custom_records_block({}, overlay) == {}


def _reviewer_defined_overlay() -> dict:
    return {
        "custom_records": {
            "quotes": {
                "definition": {
                    "label": "Quotes",
                    "schema": [
                        {"name": "speaker", "label": "Speaker", "type": "string"},
                        {"name": "quote_text", "label": "Quote text", "type": "string"},
                    ],
                },
                "user_added": [
                    {
                        "key": "user_record:1",
                        "fields": {"speaker": "Mayor Lee", "quote_text": "We will rebuild."},
                    }
                ],
            }
        }
    }


class TestReviewerDefinedRecordTypes:
    def test_definition_is_overlay_content(self) -> None:
        overlay = {
            "custom_records": {
                "quotes": {
                    "definition": {
                        "label": "Quotes",
                        "schema": [{"name": "speaker", "type": "string"}],
                    }
                }
            }
        }
        assert custom_records_overlay_has_content(overlay)

    def test_invalid_definitions_are_dropped(self) -> None:
        assert not custom_records_overlay_has_content(
            {"custom_records": {"quotes": {"definition": {"label": "Quotes", "schema": []}}}}
        )
        assert not custom_records_overlay_has_content(
            {
                "custom_records": {
                    "quotes": {
                        "definition": {"schema": [{"name": "key", "type": "string"}]},
                    }
                }
            }
        )
        assert not custom_records_overlay_has_content(
            {
                "custom_records": {
                    "Bad Type!": {
                        "definition": {"schema": [{"name": "speaker", "type": "string"}]},
                    }
                }
            }
        )

    def test_definition_field_defaults(self) -> None:
        overlay = {
            "custom_records": {
                "quotes": {
                    "definition": {
                        "schema": [{"name": "speaker_name", "type": "bogus_type"}],
                    },
                    "user_added": [{"key": "user_record:1", "fields": {"speaker_name": "Lee"}}],
                }
            }
        }
        merged = merge_custom_records_block({}, overlay)
        record_set = merged["quotes"]
        assert record_set["label"] == "Quotes"
        assert record_set["schema"] == [
            {"name": "speaker_name", "label": "Speaker name", "type": "string"}
        ]

    def test_merge_synthesizes_record_set(self) -> None:
        merged = merge_custom_records_block({}, _reviewer_defined_overlay())
        record_set = merged["quotes"]
        assert record_set["label"] == "Quotes"
        assert [spec["name"] for spec in record_set["schema"]] == ["speaker", "quote_text"]
        assert len(record_set["records"]) == 1
        assert record_set["records"][0]["source"] == "review"
        assert record_set["records"][0]["fields"]["speaker"] == "Mayor Lee"

    def test_model_block_wins_over_definition(self) -> None:
        overlay = {
            "custom_records": {
                "ingredients": {
                    "definition": {
                        "label": "Other label",
                        "schema": [{"name": "different", "type": "string"}],
                    },
                    "user_added": [
                        {"key": "user_record:1", "fields": {"name": "Sugar"}}
                    ],
                }
            }
        }
        merged = merge_custom_records_block({"ingredients": _ingredients_set()}, overlay)
        record_set = merged["ingredients"]
        assert record_set["label"] == "Ingredients"
        assert len(record_set["records"]) == 3

    def test_reviewed_block_includes_reviewer_defined_type(self) -> None:
        merged = reviewed_custom_records_block({}, _reviewer_defined_overlay())
        assert "quotes" in merged
        assert merged["quotes"]["records"][0]["fields"]["speaker"] == "Mayor Lee"

    def test_apply_to_output_creates_block_when_missing(self) -> None:
        output = {"json_output": {"consolidated": {"headline": "Story"}}}
        apply_custom_records_overlay_to_output(output, _reviewer_defined_overlay())
        block = output["json_output"]["consolidated"]["custom_records"]
        assert block["quotes"]["records"][0]["fields"]["speaker"] == "Mayor Lee"

    def test_apply_to_output_appends_to_existing_block(self) -> None:
        output = {
            "custom_extract": {"custom_records": {"ingredients": _ingredients_set()}},
        }
        apply_custom_records_overlay_to_output(output, _reviewer_defined_overlay())
        block = output["custom_extract"]["custom_records"]
        assert "ingredients" in block
        assert "quotes" in block
