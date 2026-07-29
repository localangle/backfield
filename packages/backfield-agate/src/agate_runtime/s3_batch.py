"""Shared S3 listing and JSON validation for S3Input (no boto client construction here)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agate_runtime.nodes.json_input import resolve_document_body_text


@dataclass(frozen=True)
class S3ObjectListing:
    """One ``*.json`` object from ``list_objects_v2`` (current revision only)."""

    key: str
    etag: str | None = None
    size_bytes: int | None = None
    last_modified: datetime | None = None


def logical_item_id(*, bucket: str, key: str) -> str:
    """Stable logical identity for an S3 object under a source configuration."""
    return f"{bucket}/{key}"


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def listing_metadata_matches_succeeded(
    *,
    listing: S3ObjectListing,
    stored_etag: str | None,
    stored_size_bytes: int | None,
    stored_last_modified: datetime | None,
) -> bool:
    """True when list metadata matches a prior succeeded ledger row (discovery only)."""
    if stored_etag is None and stored_size_bytes is None and stored_last_modified is None:
        return False
    if _normalize_etag(listing.etag) != _normalize_etag(stored_etag):
        return False
    if listing.size_bytes != stored_size_bytes:
        return False
    if _normalize_last_modified(listing.last_modified) != _normalize_last_modified(
        stored_last_modified
    ):
        return False
    return True


def _normalize_etag(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned.startswith('"') and cleaned.endswith('"') and len(cleaned) >= 2:
        cleaned = cleaned[1:-1]
    return cleaned or None


def _normalize_last_modified(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    # Compare at second resolution; S3 listing and stored values may differ in tz form.
    if value.tzinfo is None:
        return value.replace(microsecond=0)
    return value.astimezone(tz=value.tzinfo).replace(microsecond=0)


def list_json_objects_under_prefix(
    s3_client: Any, *, bucket: str, prefix: str
) -> list[S3ObjectListing]:
    """Return sorted ``*.json`` object listings under ``prefix`` (paginated)."""
    objects: list[S3ObjectListing] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3_client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            key = str(obj.get("Key") or "")
            if not key.endswith(".json") or key.endswith("/"):
                continue
            size_raw = obj.get("Size")
            size_bytes: int | None
            try:
                size_bytes = int(size_raw) if size_raw is not None else None
            except (TypeError, ValueError):
                size_bytes = None
            etag_raw = obj.get("ETag")
            etag = str(etag_raw) if etag_raw is not None else None
            last_modified = obj.get("LastModified")
            if last_modified is not None and not isinstance(last_modified, datetime):
                last_modified = None
            objects.append(
                S3ObjectListing(
                    key=key,
                    etag=etag,
                    size_bytes=size_bytes,
                    last_modified=last_modified,
                )
            )
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
        if not token:
            break
    objects.sort(key=lambda item: item.key)
    return objects


def list_json_keys_under_prefix(s3_client: Any, *, bucket: str, prefix: str) -> list[str]:
    """Return sorted ``*.json`` object keys under ``prefix`` (paginated)."""
    return [
        obj.key
        for obj in list_json_objects_under_prefix(s3_client, bucket=bucket, prefix=prefix)
    ]


def parse_s3_text_json_document(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse S3 body as JSON with a non-empty article body (see ``resolve_document_body_text``).

    Returns ``(document_dict, None)`` on success. The returned dict's ``text`` key is set to
    the resolved body string so batch items match JSONInput normalization.

    Returns ``(None, error_reason)`` on failure.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"invalid_json: {exc}"

    if not isinstance(data, dict):
        return None, "json_not_object"

    resolved = resolve_document_body_text(data)
    if not resolved:
        return None, "missing_or_empty_text"

    out = dict(data)
    out["text"] = resolved
    return out, None


def s3_max_files_from_params(
    params: dict[str, Any],
    *,
    default: int = 500,
    cap: int = 10_000,
) -> int:
    raw = params.get("max_files", default)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = default
    return max(1, min(n, cap))


def graph_spec_json_contains_s3_input(spec_json: str) -> bool:
    """Return True if graph JSON has at least one ``S3Input`` node (API / worker routing)."""
    try:
        data = json.loads(spec_json)
    except json.JSONDecodeError:
        return False
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return False
    for node in nodes:
        if isinstance(node, dict) and node.get("type") == "S3Input":
            return True
    return False
