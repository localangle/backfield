"""Shared S3 listing and JSON validation for S3Input (no boto client construction here)."""

from __future__ import annotations

import json
from typing import Any


def list_json_keys_under_prefix(s3_client: Any, *, bucket: str, prefix: str) -> list[str]:
    """Return sorted ``*.json`` object keys under ``prefix`` (paginated)."""
    keys: list[str] = []
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = s3_client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents") or []:
            key = str(obj.get("Key") or "")
            if key.endswith(".json") and not key.endswith("/"):
                keys.append(key)
        if not resp.get("IsTruncated"):
            break
        token = resp.get("NextContinuationToken")
        if not token:
            break
    return sorted(keys)


def parse_s3_text_json_document(raw: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse S3 body as JSON with non-empty top-level ``text`` string.

    Returns ``(document_dict, None)`` on success, else ``(None, error_reason)``.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"invalid_json: {e}"

    if not isinstance(data, dict):
        return None, "json_not_object"

    text_val = data.get("text")
    if text_val is None or not str(text_val).strip():
        return None, "missing_or_empty_text"

    return data, None


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
    for n in nodes:
        if isinstance(n, dict) and n.get("type") == "S3Input":
            return True
    return False
