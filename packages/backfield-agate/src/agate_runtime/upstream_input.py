"""Flatten namespaced executor inputs for downstream LLM and enrich nodes."""

from __future__ import annotations

from typing import Any


def merge_upstream_payload(merged: dict[str, Any], payload: dict[str, Any]) -> None:
    """Shallow merge one upstream payload, deep-merging ``custom_records``."""
    for key, value in payload.items():
        if (
            key == "custom_records"
            and isinstance(value, dict)
            and isinstance(merged.get(key), dict)
        ):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value


def expand_gathered_payload(merged: dict[str, Any]) -> dict[str, Any]:
    """Hoist branch payloads nested under ``gathered`` for downstream nodes."""
    if not isinstance(merged, dict):
        return merged
    gathered = merged.get("gathered")
    if not isinstance(gathered, dict):
        return merged
    expanded = {key: value for key, value in merged.items() if key != "gathered"}
    for payload in gathered.values():
        if isinstance(payload, dict):
            merge_upstream_payload(expanded, payload)
    return expanded


def _is_namespaced_node_key(key: str) -> bool:
    return key.startswith("node-") and len(key) > 5 and key[5:].isdigit()


def flatten_upstream_inputs(input_dict: dict[str, Any]) -> dict[str, Any]:
    """Unwrap ``node-*`` namespaces and expand Gather ``gathered`` branch payloads."""
    flattened: dict[str, Any] = {}
    for key, value in input_dict.items():
        if isinstance(value, dict) and (_is_namespaced_node_key(key) or key.isdigit()):
            merge_upstream_payload(flattened, value)
        elif isinstance(value, dict) and key == "custom_records":
            merge_upstream_payload(flattened, {key: value})
        elif isinstance(value, dict):
            merge_upstream_payload(flattened, value)
        else:
            flattened[key] = value
    return expand_gathered_payload(flattened)
