"""Unit tests for processed item automatic connections summary."""

from __future__ import annotations

from backfield_entities.connections.processed_item import (
    build_processed_item_connections_summary,
    extract_db_output_connections,
)


def test_extract_db_output_connections_from_stylebook_output() -> None:
    raw = extract_db_output_connections(
        {
            "stylebook_output": {
                "connections": {
                    "enabled": True,
                    "eligible": True,
                    "status": "succeeded",
                    "created": 1,
                    "edges": [],
                }
            }
        }
    )
    assert raw is not None
    assert raw["enabled"] is True


def test_build_summary_disabled_when_toggle_off() -> None:
    summary = build_processed_item_connections_summary(
        item_status="succeeded",
        result_obj={
            "stylebook_output": {
                "connections": {"enabled": False, "status": "disabled"},
            }
        },
    )
    assert summary["status"] == "disabled"
    assert summary["enabled"] is False


def test_build_summary_ineligible_when_gates_fail() -> None:
    summary = build_processed_item_connections_summary(
        item_status="succeeded",
        result_obj={
            "stylebook_output": {
                "connections": {
                    "enabled": True,
                    "eligible": False,
                    "status": "ineligible",
                    "reason": "stylebook_matching_off",
                }
            }
        },
    )
    assert summary["status"] == "ineligible"
    assert summary["created_count"] == 0


def test_build_summary_succeeded_with_edges() -> None:
    summary = build_processed_item_connections_summary(
        item_status="succeeded",
        result_obj={
            "stylebook_output": {
                "connections": {
                    "enabled": True,
                    "eligible": True,
                    "status": "succeeded",
                    "created": 1,
                    "edges": [
                        {
                            "from_display_name": "Jane Smith",
                            "to_display_name": "Chicago City Hall",
                            "nature": "works_for",
                            "confidence": 0.95,
                        }
                    ],
                }
            }
        },
    )
    assert summary["status"] == "succeeded"
    assert summary["created_count"] == 1
    assert summary["edges"][0]["nature"] == "works_for"


def test_build_summary_failed_preserves_error() -> None:
    summary = build_processed_item_connections_summary(
        item_status="succeeded",
        result_obj={
            "stylebook_output": {
                "connections": {
                    "enabled": True,
                    "eligible": True,
                    "status": "failed",
                    "error": "provider timeout",
                    "created": 0,
                    "edges": [],
                }
            }
        },
    )
    assert summary["status"] == "failed"
    assert summary["error"] == "provider timeout"
