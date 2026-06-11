"""Persist custom extracted records from consolidated DBOutput payloads."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from backfield_db import SubstrateCustomRecord
from sqlmodel import Session, select

from backfield_entities.ingest.db_output_settings import ReconciliationPolicy

CustomRecordPersistStatus = Literal["not_present", "skipped", "succeeded", "failed"]


def _custom_records_block(consolidated: dict[str, Any]) -> dict[str, Any] | None:
    raw = consolidated.get("custom_records")
    return raw if isinstance(raw, dict) else None


def _normalize_confidence(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value < 0.0 or value > 1.0:
        return None
    return value


def _valid_records(record_set: dict[str, Any], *, record_type: str) -> tuple[list[dict], list[str]]:
    """Filter the record list to rows with fields and at least one mention."""
    raw_records = record_set.get("records")
    if raw_records is None:
        return [], [f"custom_records[{record_type}] is missing a records list"]
    if not isinstance(raw_records, list):
        return [], [f"custom_records[{record_type}].records must be an array"]

    records: list[dict] = []
    warnings: list[str] = []
    for index, raw in enumerate(raw_records):
        if not isinstance(raw, dict):
            warnings.append(f"custom_records[{record_type}].records[{index}] must be an object")
            continue
        fields = raw.get("fields")
        if not isinstance(fields, dict) or not fields:
            warnings.append(
                f"custom_records[{record_type}].records[{index}].fields must be a non-empty object"
            )
            continue
        mentions = raw.get("mentions")
        if not isinstance(mentions, list) or not mentions:
            warnings.append(
                f"custom_records[{record_type}].records[{index}] requires at least one mention"
            )
            continue
        records.append(raw)
    return records, warnings


def _persist_record_type(
    session: Session,
    *,
    article_id: int,
    record_type: str,
    record_set: dict[str, Any],
    policy: ReconciliationPolicy,
    source_run_id: str | None,
    now: datetime,
) -> dict[str, Any]:
    """Replace all rows for one ``(article_id, record_type)`` pair."""
    records, warnings = _valid_records(record_set, record_type=record_type)

    field_schema = record_set.get("schema")
    if not isinstance(field_schema, list):
        return {
            "record_type": record_type,
            "status": "failed",
            "persisted": False,
            "error": f"custom_records[{record_type}].schema must be a list of field definitions",
        }

    existing_rows = session.exec(
        select(SubstrateCustomRecord).where(
            SubstrateCustomRecord.article_id == article_id,
            SubstrateCustomRecord.record_type == record_type,
        )
    ).all()

    if policy == "add_only" and existing_rows:
        return {
            "record_type": record_type,
            "status": "skipped",
            "persisted": False,
            "reason": "add_only",
            "count": 0,
        }

    for row in existing_rows:
        session.delete(row)
    session.flush()

    for index, raw in enumerate(records):
        session.add(
            SubstrateCustomRecord(
                article_id=article_id,
                record_type=record_type,
                record_index=index,
                fields_json=dict(raw["fields"]),
                mentions_json=list(raw["mentions"]),
                field_schema_json=list(field_schema),
                confidence=_normalize_confidence(raw.get("confidence")),
                source_run_id=source_run_id,
                created_at=now,
                updated_at=now,
            )
        )
    session.flush()

    summary: dict[str, Any] = {
        "record_type": record_type,
        "status": "succeeded",
        "persisted": bool(records) or bool(existing_rows),
        "action": "replaced" if existing_rows else "created",
        "count": len(records),
    }
    if warnings:
        summary["warnings"] = warnings
    return summary


def persist_custom_records_after_db_output(
    session: Session,
    *,
    article_id: int,
    consolidated: dict[str, Any],
    policy: ReconciliationPolicy,
    source_run_id: str | None = None,
) -> dict[str, Any]:
    """Replace ``substrate_custom_record`` rows per record type present in the payload.

    Record types absent from the consolidated payload are left untouched, so flows
    that extract only one record type never clobber another flow's records.
    """
    block = _custom_records_block(consolidated)
    if block is None or not block:
        return {"status": "not_present", "persisted": False, "count": 0}

    now = datetime.now(UTC)
    type_summaries: list[dict[str, Any]] = []
    for record_type, record_set in block.items():
        if not isinstance(record_set, dict):
            type_summaries.append(
                {
                    "record_type": str(record_type),
                    "status": "failed",
                    "persisted": False,
                    "error": f"custom_records[{record_type}] must be an object",
                }
            )
            continue
        type_summaries.append(
            _persist_record_type(
                session,
                article_id=article_id,
                record_type=str(record_type),
                record_set=record_set,
                policy=policy,
                source_run_id=source_run_id,
                now=now,
            )
        )

    statuses = {summary["status"] for summary in type_summaries}
    if statuses == {"failed"}:
        status: CustomRecordPersistStatus = "failed"
    elif "succeeded" in statuses:
        status = "succeeded"
    else:
        status = "skipped"

    return {
        "status": status,
        "persisted": any(summary.get("persisted") for summary in type_summaries),
        "count": sum(summary.get("count", 0) for summary in type_summaries),
        "record_types": type_summaries,
    }
