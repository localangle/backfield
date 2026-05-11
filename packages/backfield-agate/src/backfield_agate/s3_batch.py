"""Shared S3 listing and JSON validation for S3Input (no boto client construction here)."""

from __future__ import annotations

import json
from typing import Any

from backfield_agate.nodes.json_input import resolve_document_body_text


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
