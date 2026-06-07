"""API tests for processed item automatic connections summary."""

from __future__ import annotations

from api.routers.runs import ProcessedItemConnectionsOut, _processed_item_connections


def test_processed_item_connections_out_shape() -> None:
    out = ProcessedItemConnectionsOut.model_validate(
        {
            "status": "succeeded",
            "enabled": True,
            "created_count": 1,
            "edges": [
                {
                    "from_display_name": "Jane Smith",
                    "to_display_name": "Chicago City Hall",
                    "nature": "works_for",
                    "confidence": 0.95,
                }
            ],
            "error": None,
        }
    )
    assert out.status == "succeeded"
    assert out.created_count == 1
    assert out.edges[0].nature == "works_for"


def test_processed_item_connections_helper_disabled() -> None:
    out = _processed_item_connections(
        item_status="succeeded",
        output_obj={"stylebook_output": {"success": True}},
    )
    assert out.status == "disabled"
    assert out.enabled is False


def test_processed_item_connections_helper_succeeded_edges() -> None:
    out = _processed_item_connections(
        item_status="succeeded",
        output_obj={
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
    assert out.status == "succeeded"
    assert out.created_count == 1
    assert out.edges[0].from_display_name == "Jane Smith"


def test_processed_item_connections_helper_pending_follows_item_status() -> None:
    out = _processed_item_connections(item_status="pending", output_obj=None)
    assert out.status == "pending"
