"""Atomic claim / terminalize helpers for the S3 Input ingestion ledger."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from agate_runtime.s3_batch import (
    S3ObjectListing,
    listing_metadata_matches_succeeded,
    logical_item_id,
)
from backfield_db import AgateS3IngestionLedger
from backfield_entities.ingest.article_external_identity import (
    S3_INGESTION_EXTERNAL_SOURCE as S3_INGESTION_EXTERNAL_SOURCE,
)
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select, update

LEDGER_STATUS_PROCESSING = "processing"
LEDGER_STATUS_SUCCEEDED = "succeeded"
LEDGER_STATUS_FAILED = "failed"


@dataclass(frozen=True)
class LedgerClaimResult:
    ledger_id: str
    claim_token: str


def ensure_s3_input_source_id(
    *,
    params: dict[str, Any],
    graph_spec_json: str,
) -> tuple[str, str, dict[str, Any]]:
    """Return ``(source_id, updated_spec_json, updated_params)``, minting if needed."""
    existing = str(params.get("source_id") or "").strip()
    if existing:
        return existing, graph_spec_json, params

    source_id = str(uuid4())
    updated_params = dict(params)
    updated_params["source_id"] = source_id
    updated_spec = _set_first_s3_input_source_id(graph_spec_json, source_id)
    return source_id, updated_spec, updated_params


def _set_first_s3_input_source_id(spec_json: str, source_id: str) -> str:
    data = json.loads(spec_json)
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return spec_json
    for node in nodes:
        if not isinstance(node, dict) or node.get("type") != "S3Input":
            continue
        params = node.get("params")
        if not isinstance(params, dict):
            params = {}
            node["params"] = params
        params["source_id"] = source_id
        break
    return json.dumps(data)


def find_succeeded_matching_metadata(
    session: Session,
    *,
    project_id: int,
    source_id: str,
    item_id: str,
    listing: S3ObjectListing,
) -> AgateS3IngestionLedger | None:
    rows = list(
        session.exec(
            select(AgateS3IngestionLedger).where(
                AgateS3IngestionLedger.project_id == project_id,
                AgateS3IngestionLedger.source_id == source_id,
                AgateS3IngestionLedger.logical_item_id == item_id,
                AgateS3IngestionLedger.status == LEDGER_STATUS_SUCCEEDED,
            )
        ).all()
    )
    for row in rows:
        if listing_metadata_matches_succeeded(
            listing=listing,
            stored_etag=row.etag,
            stored_size_bytes=row.size_bytes,
            stored_last_modified=row.last_modified,
        ):
            return row
    return None


def find_row_for_fingerprint(
    session: Session,
    *,
    project_id: int,
    source_id: str,
    item_id: str,
    content_fingerprint: str,
) -> AgateS3IngestionLedger | None:
    return session.exec(
        select(AgateS3IngestionLedger).where(
            AgateS3IngestionLedger.project_id == project_id,
            AgateS3IngestionLedger.source_id == source_id,
            AgateS3IngestionLedger.logical_item_id == item_id,
            AgateS3IngestionLedger.content_fingerprint == content_fingerprint,
        )
    ).first()


def claim_ledger_revision(
    session: Session,
    *,
    project_id: int,
    source_id: str,
    bucket: str,
    key: str,
    content_fingerprint: str,
    listing: S3ObjectListing,
    version_id: str | None,
    flow_run_id: str,
    lease_duration: timedelta,
    now: datetime | None = None,
    reclaim_succeeded: bool = False,
) -> LedgerClaimResult | None:
    """Atomically claim a revision for processing, or return None if not claimable."""
    claimed_at = now or datetime.now(UTC)
    lease_expires_at = claimed_at + lease_duration
    claim_token = str(uuid4())
    item_id = logical_item_id(bucket=bucket, key=key)

    existing = find_row_for_fingerprint(
        session,
        project_id=project_id,
        source_id=source_id,
        item_id=item_id,
        content_fingerprint=content_fingerprint,
    )
    if existing is None:
        row = AgateS3IngestionLedger(
            project_id=project_id,
            source_id=source_id,
            logical_item_id=item_id,
            bucket=bucket,
            key=key,
            version_id=version_id,
            content_fingerprint=content_fingerprint,
            etag=_normalize_etag(listing.etag),
            size_bytes=listing.size_bytes,
            last_modified=listing.last_modified,
            status=LEDGER_STATUS_PROCESSING,
            claim_token=claim_token,
            lease_expires_at=lease_expires_at,
            attempt_count=1,
            flow_run_id=flow_run_id,
            first_seen_at=claimed_at,
            started_at=claimed_at,
            completed_at=None,
            last_error=None,
        )
        try:
            with session.begin_nested():
                session.add(row)
                session.flush()
        except IntegrityError:
            return None
        return LedgerClaimResult(ledger_id=str(row.id), claim_token=claim_token)

    if existing.status == LEDGER_STATUS_SUCCEEDED and not reclaim_succeeded:
        return None

    lease = existing.lease_expires_at
    if lease is not None and lease.tzinfo is None:
        lease = lease.replace(tzinfo=UTC)
    if existing.status == LEDGER_STATUS_PROCESSING and lease is not None and lease > claimed_at:
        return None

    reclaimable_statuses = (
        LEDGER_STATUS_FAILED,
        LEDGER_STATUS_PROCESSING,
        *((LEDGER_STATUS_SUCCEEDED,) if reclaim_succeeded else ()),
    )
    if existing.status not in reclaimable_statuses:
        return None

    observed_status = existing.status
    reclaim_filter = [
        AgateS3IngestionLedger.id == existing.id,
        AgateS3IngestionLedger.project_id == project_id,
        AgateS3IngestionLedger.status == observed_status,
    ]
    if observed_status == LEDGER_STATUS_PROCESSING:
        reclaim_filter.append(
            (AgateS3IngestionLedger.lease_expires_at.is_(None))
            | (AgateS3IngestionLedger.lease_expires_at <= claimed_at)
        )

    result = session.execute(
        update(AgateS3IngestionLedger)
        .where(*reclaim_filter)
        .values(
            status=LEDGER_STATUS_PROCESSING,
            claim_token=claim_token,
            lease_expires_at=lease_expires_at,
            attempt_count=int(existing.attempt_count or 0) + 1,
            flow_run_id=flow_run_id,
            version_id=version_id,
            etag=_normalize_etag(listing.etag),
            size_bytes=listing.size_bytes,
            last_modified=listing.last_modified,
            started_at=claimed_at,
            completed_at=None,
            last_error=None,
            processed_item_id=None,
        )
        .execution_options(synchronize_session=False)
    )
    if int(result.rowcount or 0) != 1:
        return None
    return LedgerClaimResult(ledger_id=str(existing.id), claim_token=claim_token)


def attach_processed_item(
    session: Session,
    *,
    project_id: int,
    ledger_id: str,
    claim_token: str,
    processed_item_id: int,
) -> None:
    session.execute(
        update(AgateS3IngestionLedger)
        .where(
            AgateS3IngestionLedger.id == ledger_id,
            AgateS3IngestionLedger.project_id == project_id,
            AgateS3IngestionLedger.claim_token == claim_token,
            AgateS3IngestionLedger.status == LEDGER_STATUS_PROCESSING,
        )
        .values(processed_item_id=processed_item_id)
        .execution_options(synchronize_session=False)
    )


def mark_ledger_succeeded(
    session: Session,
    *,
    ledger_id: str,
    claim_token: str,
    processed_item_id: int,
    now: datetime | None = None,
) -> bool:
    completed_at = now or datetime.now(UTC)
    result = session.execute(
        update(AgateS3IngestionLedger)
        .where(
            AgateS3IngestionLedger.id == ledger_id,
            AgateS3IngestionLedger.claim_token == claim_token,
            AgateS3IngestionLedger.status == LEDGER_STATUS_PROCESSING,
        )
        .values(
            status=LEDGER_STATUS_SUCCEEDED,
            completed_at=completed_at,
            last_error=None,
            processed_item_id=processed_item_id,
            lease_expires_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0) == 1


def mark_ledger_failed(
    session: Session,
    *,
    ledger_id: str,
    claim_token: str,
    processed_item_id: int,
    error_message: str | None,
    now: datetime | None = None,
) -> bool:
    completed_at = now or datetime.now(UTC)
    result = session.execute(
        update(AgateS3IngestionLedger)
        .where(
            AgateS3IngestionLedger.id == ledger_id,
            AgateS3IngestionLedger.claim_token == claim_token,
            AgateS3IngestionLedger.status == LEDGER_STATUS_PROCESSING,
        )
        .values(
            status=LEDGER_STATUS_FAILED,
            completed_at=completed_at,
            last_error=(error_message or "")[:4000] or None,
            processed_item_id=processed_item_id,
            lease_expires_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0) == 1


def load_claim_token(
    session: Session,
    *,
    ledger_id: str,
) -> str | None:
    row = session.get(AgateS3IngestionLedger, ledger_id)
    if row is None or row.status != LEDGER_STATUS_PROCESSING:
        return None
    token = row.claim_token
    return str(token) if token else None


def _normalize_etag(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned.startswith('"') and cleaned.endswith('"') and len(cleaned) >= 2:
        cleaned = cleaned[1:-1]
    return cleaned or None
