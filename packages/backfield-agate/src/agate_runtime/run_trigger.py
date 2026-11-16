"""Shared Agate run trigger: apply ingress inputs, pin effective spec, enqueue worker tasks."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from backfield_ai.credentials import merge_project_and_org_llm_api_keys
from backfield_db import AgateGraph, AgateProcessedItem, AgateRun
from sqlmodel import Session

from agate_runtime.graph_validation import validate_graph_invariants
from agate_runtime.json_input_batch import graph_spec_json_contains_json_input_batch
from agate_runtime.nodes.json_input import json_input_output_from_dict
from agate_runtime.run_graph_spec import merge_run_result_payload
from agate_runtime.s3_batch import (
    empty_s3_prefix_message,
    first_s3_input_params,
    graph_spec_json_contains_s3_input,
    prefix_has_json_object,
    s3_input_bucket_and_prefix,
    s3_max_files_from_params,
)
from agate_runtime.s3_credentials import env_overlay, s3_client_from_env
from agate_runtime.single_item import build_single_item_input_from_graph_spec_json
from agate_runtime.types import GraphSpec, NodeConfig

PUBLIC_ALIAS_PARAM = "public_alias"
_INGRESS_NODE_TYPES: frozenset[str] = frozenset({"TextInput", "JSONInput", "S3Input"})
_S3_PREFLIGHT_MISSING_CREDENTIALS = (
    "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set for S3Input batch listing."
)


@dataclass(frozen=True)
class TriggerRunResult:
    run: AgateRun
    processed_item: AgateProcessedItem | None = None
    enqueue_task_name: str | None = None
    enqueue_args: list[Any] | None = None

    def enqueue(self, enqueue_task: Callable[[str, list[Any]], None]) -> None:
        if self.enqueue_task_name is not None and self.enqueue_args is not None:
            enqueue_task(self.enqueue_task_name, self.enqueue_args)


def find_public_ingress_node(spec: GraphSpec) -> NodeConfig:
    """Return the single input-category node in the graph."""
    ingress = [node for node in spec.nodes if node.type in _INGRESS_NODE_TYPES]
    if not ingress:
        raise ValueError(
            "Run requires exactly one TextInput, JSONInput, or S3Input node in the graph."
        )
    if len(ingress) > 1:
        raise ValueError(
            "Run requires exactly one ingress node; "
            f"found {len(ingress)} ({', '.join(n.type for n in ingress)})."
        )
    return ingress[0]


def _ingress_public_alias(node: NodeConfig) -> str:
    raw = node.params.get(PUBLIC_ALIAS_PARAM)
    if raw is None:
        return ""
    return str(raw).strip()


def _apply_text_input_override(params: dict[str, Any], arg: Any) -> dict[str, Any]:
    if not isinstance(arg, dict):
        raise ValueError("TextInput input must be an object with a non-empty 'text' field.")
    text = arg.get("text")
    if text is None or not str(text).strip():
        raise ValueError("TextInput input requires a non-empty 'text' field.")
    return {**params, "text": str(text)}


def _apply_json_input_override(params: dict[str, Any], arg: Any) -> dict[str, Any]:
    if not isinstance(arg, dict):
        raise ValueError("JSONInput input must be a JSON object.")
    normalized = json_input_output_from_dict(dict(arg))
    if not str(normalized.get("text") or "").strip():
        raise ValueError("JSONInput input requires a resolvable non-empty article body.")
    return normalized


def _apply_s3_input_override(params: dict[str, Any], arg: Any) -> dict[str, Any]:
    if arg is not None and not isinstance(arg, dict):
        raise ValueError("S3Input input must be an object.")
    merged = dict(params)
    if isinstance(arg, dict):
        if "bucket" in arg:
            bucket = str(arg.get("bucket") or "").strip()
            if not bucket:
                raise ValueError("S3Input input 'bucket' must be non-empty when provided.")
            merged["bucket"] = bucket
        if "prefix" in arg:
            merged["folder_path"] = str(arg.get("prefix") or "").strip()
        if "max_files" in arg:
            merged["max_files"] = arg["max_files"]
    capped = s3_max_files_from_params(merged)
    merged["max_files"] = capped
    bucket = str(merged.get("bucket") or "").strip()
    if not bucket:
        raise ValueError("S3Input requires a non-empty bucket before running the flow.")
    return merged


def apply_inputs_to_spec(
    spec: GraphSpec,
    inputs: dict[str, Any] | None,
) -> GraphSpec:
    """Return a copy of ``spec`` with the ingress node's params overridden by ``inputs``."""
    if not inputs:
        return spec

    if len(inputs) != 1:
        keys = ", ".join(sorted(inputs))
        raise ValueError(
            f"inputs must contain exactly one alias key; got {len(inputs)} ({keys})."
        )

    ingress = find_public_ingress_node(spec)
    alias = _ingress_public_alias(ingress)
    if not alias:
        raise ValueError(
            "Ingress node is missing public_alias; set it on the node before passing inputs."
        )

    (provided_alias, arg) = next(iter(inputs.items()))
    if provided_alias != alias:
        raise ValueError(
            f"Unknown input alias {provided_alias!r}; expected {alias!r} for this graph."
        )

    params = dict(ingress.params) if isinstance(ingress.params, dict) else {}
    if ingress.type == "TextInput":
        new_params = _apply_text_input_override(params, arg)
    elif ingress.type == "JSONInput":
        new_params = _apply_json_input_override(params, arg)
    elif ingress.type == "S3Input":
        new_params = _apply_s3_input_override(params, arg)
    else:
        raise ValueError(f"Unsupported ingress node type: {ingress.type!r}")

    updated_nodes: list[NodeConfig] = []
    for node in spec.nodes:
        if node.id == ingress.id:
            updated_nodes.append(
                NodeConfig(
                    id=node.id,
                    type=node.type,
                    params=new_params,
                    position=node.position,
                )
            )
        else:
            updated_nodes.append(node)

    return GraphSpec(name=spec.name, nodes=updated_nodes, edges=list(spec.edges))


def preflight_s3_batch_has_json_objects(
    session: Session,
    *,
    project_id: int,
    spec: GraphSpec,
) -> None:
    """Raise ``ValueError`` when the S3Input prefix has no ``*.json`` objects.

    Uses project/org integration secrets (same source as the worker). Does not create a run.
    """
    bucket, prefix = s3_input_bucket_and_prefix(first_s3_input_params(spec))
    overlay = merge_project_and_org_llm_api_keys(session, int(project_id))
    with env_overlay(overlay):
        s3_client = s3_client_from_env(
            missing_credentials_message=_S3_PREFLIGHT_MISSING_CREDENTIALS
        )
        has_json = prefix_has_json_object(s3_client, bucket=bucket, prefix=prefix)
    if not has_json:
        raise ValueError(empty_s3_prefix_message(bucket=bucket, prefix=prefix))


def trigger_agate_run(
    session: Session,
    *,
    graph: AgateGraph,
    inputs: dict[str, Any] | None = None,
    replace_article_geography_on_persist: bool = False,
    enqueue: Callable[[str, list[Any]], None],
    commit: bool = True,
) -> TriggerRunResult:
    """Create a run, pin the effective graph spec, and enqueue the appropriate worker task."""
    spec = GraphSpec.model_validate_json(graph.spec_json)
    validate_graph_invariants(spec)
    effective = apply_inputs_to_spec(spec, inputs)
    effective_json = effective.model_dump_json()
    is_s3_batch = graph_spec_json_contains_s3_input(effective_json)
    is_json_input_batch = (
        not is_s3_batch and graph_spec_json_contains_json_input_batch(effective_json)
    )
    input_doc: dict[str, Any] | None = None
    source_file: str | None = None
    if not is_s3_batch and not is_json_input_batch:
        input_doc, source_file = build_single_item_input_from_graph_spec_json(effective_json)

    if is_s3_batch:
        # Reject empty prefixes before inserting AgateRun so the runs list stays clean.
        preflight_s3_batch_has_json_objects(
            session,
            project_id=int(graph.project_id),
            spec=effective,
        )

    run = AgateRun(
        graph_id=graph.id,
        status="pending",
        replace_article_geography_on_persist=replace_article_geography_on_persist,
    )
    session.add(run)
    session.flush()
    session.refresh(run)

    if is_s3_batch:
        run.result_json = merge_run_result_payload(None, graph_spec_json=effective_json)
        run.updated_at = datetime.now(UTC)
        session.add(run)
        if commit:
            session.commit()
        else:
            session.flush()
        session.refresh(run)
        result = TriggerRunResult(
            run=run,
            processed_item=None,
            enqueue_task_name="worker.tasks.execute_s3_batch_setup",
            enqueue_args=[run.id],
        )
        if commit:
            result.enqueue(enqueue)
        return result

    if is_json_input_batch:
        run.result_json = merge_run_result_payload(None, graph_spec_json=effective_json)
        run.updated_at = datetime.now(UTC)
        session.add(run)
        if commit:
            session.commit()
        else:
            session.flush()
        session.refresh(run)
        result = TriggerRunResult(
            run=run,
            processed_item=None,
            enqueue_task_name="worker.tasks.execute_json_input_batch_setup",
            enqueue_args=[run.id],
        )
        if commit:
            result.enqueue(enqueue)
        return result

    item = AgateProcessedItem(
        run_id=run.id,
        source_file=source_file,
        input_json=json.dumps(input_doc),
        status="pending",
    )
    session.add(item)
    run.status = "running"
    run.result_json = merge_run_result_payload(None, graph_spec_json=effective_json)
    run.updated_at = datetime.now(UTC)
    session.add(run)
    if commit:
        session.commit()
    else:
        session.flush()
    session.refresh(item)
    session.refresh(run)

    if item.id is None:
        raise RuntimeError("Processed item id missing after save")

    result = TriggerRunResult(
        run=run,
        processed_item=item,
        enqueue_task_name="worker.tasks.execute_processed_item",
        enqueue_args=[int(item.id)],
    )
    if commit:
        result.enqueue(enqueue)
    return result
