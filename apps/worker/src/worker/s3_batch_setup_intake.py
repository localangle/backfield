"""Load one S3 prefix into a run: claim ledger revisions and add pending items per chunk."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from agate_runtime.run_graph_spec import merge_run_result_payload
from agate_runtime.s3_batch import (
    S3ObjectListing,
    logical_item_id,
    parse_s3_text_json_document,
    sha256_hex,
)
from backfield_db import AgateProcessedItem, AgateRun
from sqlmodel import Session, select

from worker.s3_batch_intake import (
    FetchedObject,
    IntakeTiming,
    fetch_object,
    fetch_objects,
    fetch_worker_count,
)
from worker.s3_ingestion_ledger import (
    attach_processed_item,
    claim_ledger_revision,
    find_row_for_fingerprint,
    unchanged_object_keys,
)

logger = logging.getLogger(__name__)


@dataclass
class S3IntakeCounters:
    """Running totals while an S3 prefix is loaded into a run."""

    skipped_invalid: int = 0
    skipped_cap: int = 0
    skipped_unchanged: int = 0
    skipped_claim_conflict: int = 0
    valid: int = 0

    def as_meta(self, total_json_objects: int, *, intake_complete: bool | None) -> dict[str, Any]:
        """``result_json.s3_batch`` payload; ``intake_complete`` is omitted when ``None``."""
        meta: dict[str, Any] = {
            "total_json_objects": total_json_objects,
            "skipped_invalid": self.skipped_invalid,
            "skipped_cap": self.skipped_cap,
            "skipped_unchanged": self.skipped_unchanged,
            "skipped_claim_conflict": self.skipped_claim_conflict,
            "valid_executed": self.valid,
        }
        if intake_complete is not None:
            meta["intake_complete"] = intake_complete
        return meta


def commit_s3_intake_progress(
    session: Session,
    run_id: str,
    spec_json: str,
    s3_batch: dict[str, Any],
) -> bool:
    """Commit pending intake rows together with the run's counters.

    Returns False (after rolling back the rows) when the run is no longer ``running``, for
    example because it was cancelled while objects were being read.
    """
    run = session.exec(
        select(AgateRun)
        .where(AgateRun.id == run_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).first()
    if run is None or run.status != "running":
        session.rollback()
        return False
    run.result_json = merge_run_result_payload(
        run.result_json,
        s3_batch=s3_batch,
        graph_spec_json=spec_json,
    )
    run.updated_at = datetime.now(UTC)
    session.add(run)
    session.commit()
    return True


def _add_processed_item_for_object(
    session: Session,
    *,
    run_id: str,
    project_id: int,
    source_id: str,
    bucket: str,
    fetched: FetchedObject,
    reprocess_unchanged: bool,
    lease_duration: timedelta,
    counters: S3IntakeCounters,
) -> tuple[int, int] | None:
    """Claim one object's ledger revision and add its pending item.

    Returns ``(item_id, text_length)``, or None after counting why the object was skipped.
    """
    listing = fetched.listing
    key = listing.key
    item_logical_id = logical_item_id(bucket=bucket, key=key)
    if fetched.error is not None or fetched.raw_bytes is None:
        counters.skipped_invalid += 1
        logger.debug(
            "S3 batch skip get failure run_id=%s key=%s err=%s",
            run_id,
            key,
            fetched.error,
        )
        return None
    raw_bytes = fetched.raw_bytes
    try:
        raw = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        counters.skipped_invalid += 1
        return None

    fingerprint = sha256_hex(raw_bytes)
    existing_fp = find_row_for_fingerprint(
        session,
        project_id=project_id,
        source_id=source_id,
        item_id=item_logical_id,
        content_fingerprint=fingerprint,
    )
    if not reprocess_unchanged and existing_fp is not None and existing_fp.status == "succeeded":
        counters.skipped_unchanged += 1
        return None
    if (
        existing_fp is not None
        and existing_fp.status == "processing"
        and existing_fp.lease_expires_at is not None
    ):
        lease = existing_fp.lease_expires_at
        if lease.tzinfo is None:
            lease = lease.replace(tzinfo=UTC)
        if lease > datetime.now(UTC):
            counters.skipped_claim_conflict += 1
            return None

    doc, err = parse_s3_text_json_document(raw)
    if err or doc is None:
        counters.skipped_invalid += 1
        return None

    claim = claim_ledger_revision(
        session,
        project_id=project_id,
        source_id=source_id,
        bucket=bucket,
        key=key,
        content_fingerprint=fingerprint,
        listing=listing,
        version_id=fetched.version_id,
        flow_run_id=run_id,
        lease_duration=lease_duration,
        reclaim_succeeded=reprocess_unchanged,
    )
    if claim is None:
        counters.skipped_claim_conflict += 1
        return None

    row = AgateProcessedItem(
        run_id=run_id,
        source_file=key,
        input_json=json.dumps(doc),
        status="pending",
        ingestion_ledger_id=claim.ledger_id,
    )
    session.add(row)
    session.flush()
    if row.id is None:
        counters.skipped_claim_conflict += 1
        return None
    attach_processed_item(
        session,
        project_id=project_id,
        ledger_id=claim.ledger_id,
        claim_token=claim.claim_token,
        processed_item_id=int(row.id),
    )
    counters.valid += 1
    return int(row.id), len(str(doc.get("text") or ""))


def ingest_s3_chunk(
    session: Session,
    *,
    run_id: str,
    project_id: int,
    source_id: str,
    bucket: str,
    s3_client: Any,
    chunk: Sequence[S3ObjectListing],
    reprocess_unchanged: bool,
    max_files: int,
    lease_duration: timedelta,
    counters: S3IntakeCounters,
    timing: IntakeTiming,
) -> list[tuple[int, int]]:
    """Add pending items for one chunk of listings (rows are flushed, not committed).

    Objects that already succeeded are skipped from one batched ledger query, and the rest are
    read from S3 in parallel. Selection order matches the listing, so ``max_files`` keeps the
    same objects as one-by-one loading. Returns ``(item_id, text_length)`` per new item.
    """
    chunk_started = time.perf_counter()
    unchanged_keys: set[str] = set()
    if not reprocess_unchanged:
        unchanged_keys = unchanged_object_keys(
            session,
            project_id=project_id,
            source_id=source_id,
            bucket=bucket,
            listings=chunk,
        )
    candidates = [listing for listing in chunk if listing.key not in unchanged_keys]
    prefetched: dict[str, FetchedObject] = {}
    fetch_s = 0.0
    if candidates and max_files - counters.valid >= len(candidates):
        # Every candidate fits under the cap, so read them all at once. Near the cap the loop
        # below reads one at a time so objects past the cap are never fetched.
        fetch_started = time.perf_counter()
        prefetched = fetch_objects(
            s3_client,
            bucket=bucket,
            listings=candidates,
            workers=fetch_worker_count(),
        )
        fetch_s += time.perf_counter() - fetch_started

    chunk_pending: list[tuple[int, int]] = []
    for listing in chunk:
        if listing.key in unchanged_keys:
            counters.skipped_unchanged += 1
            continue
        if counters.valid >= max_files:
            counters.skipped_cap += 1
            continue
        fetched = prefetched.get(listing.key)
        if fetched is None:
            fetch_started = time.perf_counter()
            fetched = fetch_object(s3_client, bucket=bucket, listing=listing)
            fetch_s += time.perf_counter() - fetch_started
        added = _add_processed_item_for_object(
            session,
            run_id=run_id,
            project_id=project_id,
            source_id=source_id,
            bucket=bucket,
            fetched=fetched,
            reprocess_unchanged=reprocess_unchanged,
            lease_duration=lease_duration,
            counters=counters,
        )
        if added is not None:
            chunk_pending.append(added)
    timing.fetch_s += fetch_s
    timing.database_s += time.perf_counter() - chunk_started - fetch_s
    return chunk_pending
