"""Compact summaries for automatic connection inference."""

from __future__ import annotations

from typing import Any

from backfield_entities.connections.inference import FamilyInferenceResult
from backfield_entities.connections.writer import AutoConnectionWriteResult, WrittenAutoConnection


def build_auto_connections_summary(
    *,
    enabled: bool,
    eligible: bool,
    reason: str,
    families: list[FamilyInferenceResult] | None = None,
    write_result: AutoConnectionWriteResult | None = None,
    created_cap_skipped: int = 0,
    error: str | None = None,
) -> dict[str, Any]:
    """Build the DBOutput ``connections`` summary payload."""
    if not enabled:
        return {"enabled": False, "status": "disabled", "reason": reason}
    if error:
        return {
            "enabled": True,
            "eligible": eligible,
            "status": "failed",
            "reason": reason,
            "error": error,
            "created": 0,
            "skipped_existing": 0,
            "families": [],
        }
    if not eligible:
        return {
            "enabled": True,
            "eligible": False,
            "status": "ineligible",
            "reason": reason,
            "created": 0,
            "skipped_existing": 0,
            "families": [],
        }

    family_summaries: list[dict[str, Any]] = []
    total_proposed = 0
    total_accepted = 0
    total_skipped = 0
    for family in families or []:
        counts = family.counts
        total_proposed += counts.proposed
        total_accepted += counts.accepted
        total_skipped += counts.skipped
        family_summaries.append(
            {
                "from_entity_type": family.from_entity_type,
                "to_entity_type": family.to_entity_type,
                "proposed": counts.proposed,
                "accepted": counts.accepted,
                "skipped": counts.skipped,
                "skip_reasons": dict(counts.skip_reasons),
            }
        )

    created_rows = write_result.created if write_result is not None else []
    return {
        "enabled": True,
        "eligible": True,
        "status": "succeeded",
        "reason": reason,
        "created": len(created_rows),
        "skipped_existing": (
            write_result.skipped_existing_count if write_result is not None else 0
        ),
        "created_cap_skipped": created_cap_skipped,
        "proposed": total_proposed,
        "accepted": total_accepted,
        "skipped": total_skipped,
        "families": family_summaries,
        "edges": [_written_edge_dict(edge) for edge in created_rows],
    }


def _written_edge_dict(edge: WrittenAutoConnection) -> dict[str, Any]:
    return {
        "from_entity_type": edge.from_entity_type,
        "from_entity_id": edge.from_entity_id,
        "from_display_name": edge.from_display_name,
        "to_entity_type": edge.to_entity_type,
        "to_entity_id": edge.to_entity_id,
        "to_display_name": edge.to_display_name,
        "description": edge.description,
        "nature": edge.nature,
        "confidence": edge.confidence,
    }
