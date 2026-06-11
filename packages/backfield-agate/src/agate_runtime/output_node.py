"""Output node — consolidated from agate-ai-platform flowbuilder (no flowbuilder_core)."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any

from pydantic import BaseModel


PREFERRED_KEY_ORDER = [
    "publication",
    "headline",
    "url",
    "author",
    "pub_date",
    "updated",
    "text",
    "images",
]


class OutputParams(BaseModel):
    exclude: list[str] | None = None
    include: list[str] | None = None


def _merge_upstream_payload(merged: dict[str, Any], payload: dict[str, Any]) -> None:
    """Shallow merge one upstream payload, deep-merging ``custom_records``.

    Custom Extract branches share the ``custom_records`` key (a dict keyed by record
    type), so parallel branches must union record types instead of clobbering.
    """
    for key, value in payload.items():
        if (
            key == "custom_records"
            and isinstance(value, dict)
            and isinstance(merged.get(key), dict)
        ):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value


def _merge_namespaced_upstream_inputs_for_dboutput(inputs: dict[str, Any]) -> dict[str, Any]:
    """Shallow-merge upstream node outputs keyed by upstream node id (DBOutput wiring)."""

    merged: dict[str, Any] = {}
    for _upstream_id, payload in inputs.items():
        if isinstance(payload, dict):
            _merge_upstream_payload(merged, payload)
    return _expand_gathered_payload(merged)


def _expand_gathered_payload(merged: dict[str, Any]) -> dict[str, Any]:
    """Hoist ``gathered`` branch payloads for OutputConsolidator / DBOutput."""
    if not isinstance(merged, dict):
        return merged
    gathered = merged.get("gathered")
    if not isinstance(gathered, dict):
        return merged
    expanded = {key: value for key, value in merged.items() if key != "gathered"}
    for payload in gathered.values():
        if isinstance(payload, dict):
            _merge_upstream_payload(expanded, payload)
    return expanded


def consolidated_body_from_dboutput(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    """Run the same consolidation path as the DBOutput node before persistence (worker or stub)."""

    merged = _merge_namespaced_upstream_inputs_for_dboutput(inputs)
    merged = expand_upstream_merge_for_output_consolidator(merged)
    cons = OutputConsolidator()
    p = OutputParams.model_validate(params)
    return cons.run(merged, p.model_dump())


def expand_upstream_merge_for_output_consolidator(merged: dict[str, Any]) -> dict[str, Any]:
    """Hoist JSON ``Output``'s ``{"consolidated": {...}}`` shell after namespaced shallow-merge.

    When ``DBOutput`` is wired directly after ``Output``, upstream merge yields a top-level
    ``consolidated`` key; :class:`OutputConsolidator` expects article-shaped keys (``places``,
    ``text``, …) at the top level like multi-upstream merges from raw nodes.
    """

    if not isinstance(merged, dict):
        return merged
    inner = merged.get("consolidated")
    if isinstance(inner, dict):
        shell = {k: v for k, v in merged.items() if k != "consolidated"}
        return {**shell, **inner}
    return dict(merged)


class OutputConsolidator:
    """Same behavior as flowbuilder Output node."""

    def _unwrap_node_data(self, data: dict[str, Any], target: dict[str, Any]) -> None:
        for key, value in data.items():
            is_node_key = key.startswith("node-") and len(key) > 5 and key[5:].isdigit()

            if is_node_key:
                if isinstance(value, dict):
                    self._unwrap_node_data(value, target)
                else:
                    target[key] = value
            else:
                if key in target and isinstance(target[key], dict) and isinstance(value, dict):
                    self._unwrap_node_data(value, target[key])
                else:
                    target[key] = value

    def _apply_filters(self, data: dict[str, Any], params: OutputParams) -> dict[str, Any]:
        exclude_set = set(params.exclude) if params.exclude else set()
        include_set = set(params.include) if params.include else None

        filtered: dict[str, Any] = {}
        for key, value in data.items():
            if key in exclude_set:
                continue
            if include_set is not None and key not in include_set:
                continue
            filtered[key] = value

        return filtered

    def _reorder_keys(self, data: dict[str, Any]) -> dict[str, Any]:
        ordered: OrderedDict[str, Any] = OrderedDict()
        for key in PREFERRED_KEY_ORDER:
            if key in data:
                ordered[key] = data[key]
        for key, value in data.items():
            if key not in ordered:
                ordered[key] = value
        return dict(ordered)

    def run(self, merged_input: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
        p = OutputParams.model_validate(params)
        filtered_data: dict[str, Any] = {}
        self._unwrap_node_data(dict(merged_input), filtered_data)
        if p.exclude or p.include:
            filtered_data = self._apply_filters(filtered_data, p)
        filtered_data = self._reorder_keys(filtered_data)
        return filtered_data
