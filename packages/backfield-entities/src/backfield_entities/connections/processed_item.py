"""Compact automatic connections summary for processed item detail."""

from __future__ import annotations

from typing import Any, Literal

ProcessedItemConnectionsStatus = Literal[
    "disabled",
    "ineligible",
    "pending",
    "running",
    "succeeded",
    "failed",
]


def extract_db_output_connections(
    result_obj: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Read ``connections`` from Backfield Output on ``stylebook_output``."""
    if not isinstance(result_obj, dict):
        return None
    block = result_obj.get("stylebook_output")
    if not isinstance(block, dict):
        return None
    raw = block.get("connections")
    return raw if isinstance(raw, dict) else None


def _empty_summary(*, status: ProcessedItemConnectionsStatus) -> dict[str, Any]:
    return {
        "status": status,
        "enabled": False,
        "created_count": 0,
        "edges": [],
        "error": None,
    }


def _normalize_edges(raw_edges: object) -> list[dict[str, Any]]:
    if not isinstance(raw_edges, list):
        return []
    out: list[dict[str, Any]] = []
    for edge in raw_edges:
        if not isinstance(edge, dict):
            continue
        from_name = str(edge.get("from_display_name") or "").strip()
        to_name = str(edge.get("to_display_name") or "").strip()
        description = str(edge.get("description") or "").strip()
        nature_raw = edge.get("nature")
        nature = str(nature_raw).strip() if nature_raw is not None else ""
        if not from_name or not to_name or (not description and not nature):
            continue
        confidence_raw = edge.get("confidence")
        confidence: float | None
        try:
            confidence = float(confidence_raw) if confidence_raw is not None else None
        except (TypeError, ValueError):
            confidence = None
        out.append(
            {
                "from_display_name": from_name,
                "to_display_name": to_name,
                "description": description or None,
                "nature": nature or None,
                "confidence": confidence,
            }
        )
    return out


def build_processed_item_connections_summary(
    *,
    item_status: str,
    result_obj: dict[str, Any] | None,
) -> dict[str, Any]:
    """Derive compact automatic connections status for processed item detail."""
    if item_status == "pending":
        return _empty_summary(status="pending")
    if item_status == "running":
        return _empty_summary(status="running")

    raw = extract_db_output_connections(result_obj)
    if raw is None or not raw.get("enabled"):
        return _empty_summary(status="disabled")

    if not raw.get("eligible"):
        return {
            "status": "ineligible",
            "enabled": True,
            "created_count": 0,
            "edges": [],
            "error": None,
        }

    output_status = str(raw.get("status") or "succeeded")
    status: ProcessedItemConnectionsStatus
    if output_status == "failed":
        status = "failed"
    else:
        status = "succeeded"

    error_raw = raw.get("error")
    error = error_raw if isinstance(error_raw, str) and error_raw.strip() else None
    created_count = int(raw.get("created") or 0)
    edges = _normalize_edges(raw.get("edges"))

    return {
        "status": status,
        "enabled": True,
        "created_count": created_count,
        "edges": edges,
        "error": error,
    }
