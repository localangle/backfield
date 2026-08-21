"""Read helpers for connection evidence (derived display fields after cutover)."""

from __future__ import annotations

from typing import Any

from backfield_db import StylebookConnectionEvidence
from sqlmodel import Session, select


def list_connection_evidence(
    session: Session,
    *,
    connection_id: int,
) -> list[StylebookConnectionEvidence]:
    rows = list(
        session.exec(
            select(StylebookConnectionEvidence).where(
                StylebookConnectionEvidence.connection_id == int(connection_id)
            )
        ).all()
    )

    def _sort_key(row: StylebookConnectionEvidence) -> tuple[float, float, int]:
        confidence = float(row.confidence) if row.confidence is not None else -1.0
        observed = row.observed_at.timestamp() if row.observed_at is not None else 0.0
        return (confidence, observed, int(row.id or 0))

    rows.sort(key=_sort_key, reverse=True)
    return rows


def best_connection_evidence(
    session: Session,
    *,
    connection_id: int,
) -> StylebookConnectionEvidence | None:
    rows = list_connection_evidence(session, connection_id=connection_id)
    return rows[0] if rows else None


def derived_connection_description(
    session: Session,
    *,
    connection_id: int,
) -> str | None:
    """Display label from best evidence (description, then quote, then reason)."""
    evidence = best_connection_evidence(session, connection_id=connection_id)
    if evidence is None:
        return None
    for value in (evidence.description, evidence.quote, evidence.reason):
        text = (value or "").strip()
        if text:
            return text
    return None


def legacy_evidence_json_for_connection(
    session: Session,
    *,
    connection_id: int,
) -> dict[str, Any] | None:
    """Best evidence shaped like the former connection ``evidence_json`` blob."""
    evidence = best_connection_evidence(session, connection_id=connection_id)
    if evidence is None:
        return None
    payload: dict[str, Any] = {}
    if evidence.source:
        payload["source"] = evidence.source
    if evidence.prompt_version:
        payload["prompt_version"] = evidence.prompt_version
    if evidence.confidence is not None:
        payload["confidence"] = float(evidence.confidence)
    if evidence.quote:
        payload["quote"] = evidence.quote
    if evidence.reason:
        payload["reason"] = evidence.reason
    if evidence.article_id is not None:
        payload["article_id"] = int(evidence.article_id)
    if evidence.run_id:
        payload["run_id"] = evidence.run_id
    if evidence.processed_item_id is not None:
        payload["processed_item_id"] = int(evidence.processed_item_id)
    if evidence.match_basis:
        payload["match_basis"] = evidence.match_basis
    if isinstance(evidence.payload_json, dict):
        for key, value in evidence.payload_json.items():
            payload.setdefault(key, value)
    return payload or None
