"""Celery tasks."""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import boto3
from backfield_ai.credentials import merge_project_and_org_llm_api_keys
from backfield_ai.tracking_context import (
    LlmAttemptTrackingContext,
    attach_llm_tracking_context,
    reset_llm_tracking_context,
    set_llm_tracking_current_node,
)
from backfield_core import GraphSpec, execute_graph
from backfield_core.nodes import NODE_RUNNERS
from backfield_core.nodes.json_input import json_input_output_from_dict
from backfield_core.s3_batch import (
    list_json_keys_under_prefix,
    parse_s3_text_json_document,
    s3_max_files_from_params,
)
from backfield_db import AgateGraph, AgateProcessedItem, AgateRun
from backfield_db.session import get_engine
from celery import Celery, chord, group
from sqlmodel import Session, select

from worker.nodes.db_output import run_db_output

logger = logging.getLogger(__name__)

celery_app = Celery(
    "agate_worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)


@contextmanager
def _env_overlay(updates: dict[str, str]):
    keys = list(updates.keys())
    previous: dict[str, str | None] = {k: os.environ.get(k) for k in keys}
    try:
        for k, v in updates.items():
            os.environ[k] = v
        yield
    finally:
        for k in keys:
            prev = previous.get(k)
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


@contextmanager
def _run_execution_env(*, project_id: int, graph_id: str, run_id: str):
    updates = {
        "BACKFIELD_PROJECT_ID": str(project_id),
        "BACKFIELD_GRAPH_ID": str(graph_id),
        "BACKFIELD_RUN_ID": str(run_id),
    }
    with _env_overlay(updates):
        yield


def _s3_client_from_env() -> Any:
    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_session_token = os.environ.get("AWS_SESSION_TOKEN")
    if not aws_access_key or not aws_secret_key:
        raise ValueError(
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set for S3Input batch listing."
        )
    session_kwargs: dict[str, str] = {
        "aws_access_key_id": aws_access_key,
        "aws_secret_access_key": aws_secret_key,
    }
    if aws_session_token:
        session_kwargs["aws_session_token"] = aws_session_token
    return boto3.client("s3", **session_kwargs)


def _first_s3_input_params(spec: GraphSpec) -> dict[str, Any]:
    for node in spec.nodes:
        if node.type == "S3Input":
            return dict(node.params)
    raise ValueError("S3 batch setup requires an S3Input node in the graph.")


def _finalize_s3_parent_run(session: Session, run_id: str) -> None:
    run = session.get(AgateRun, run_id)
    if not run:
        return
    items = list(
        session.exec(select(AgateProcessedItem).where(AgateProcessedItem.run_id == run_id)).all()
    )
    if any(row.status in ("pending", "running") for row in items):
        return
    failed = [row for row in items if row.status == "failed"]
    base: dict[str, Any] = {}
    if run.result_json:
        try:
            base = json.loads(run.result_json)
        except json.JSONDecodeError:
            base = {}
    base["items"] = [
        {
            "id": row.id,
            "source_file": row.source_file,
            "status": row.status,
            "error_message": row.error_message,
        }
        for row in items
    ]
    run.result_json = json.dumps(base)
    if failed:
        run.status = "failed"
        run.error_message = f"{len(failed)} of {len(items)} file task(s) failed."
    else:
        run.status = "succeeded"
        run.error_message = None
    run.updated_at = datetime.now(UTC)
    session.add(run)
    session.commit()


@celery_app.task(name="worker.tasks.execute_agate_run")
def execute_agate_run(run_id: str) -> None:
    engine = get_engine()
    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        if not run:
            return
        graph = session.get(AgateGraph, run.graph_id)
        if not graph:
            run.status = "failed"
            run.error_message = "Graph not found"
            run.updated_at = datetime.now(UTC)
            session.add(run)
            session.commit()
            return

        run.status = "running"
        session.add(run)
        session.commit()

        try:
            spec = GraphSpec.model_validate_json(graph.spec_json)
            overlay = merge_project_and_org_llm_api_keys(session, graph.project_id)
            node_runners = dict(NODE_RUNNERS)
            node_runners["DBOutput"] = run_db_output
            track_tok = attach_llm_tracking_context(
                LlmAttemptTrackingContext(
                    session=session,
                    project_id=graph.project_id,
                    run_id=run.id,
                )
            )
            try:
                with _env_overlay(overlay), _run_execution_env(
                    project_id=graph.project_id,
                    graph_id=graph.id,
                    run_id=run.id,
                ):
                    outputs = execute_graph(
                        spec,
                        node_runners=node_runners,
                        before_each_node=lambda nid, ntype: set_llm_tracking_current_node(
                            nid, ntype
                        ),
                    )
            finally:
                reset_llm_tracking_context(track_tok)
            run.status = "succeeded"
            run.result_json = json.dumps(outputs)
            run.error_message = None
        except Exception as e:
            run.status = "failed"
            run.error_message = str(e)
            run.result_json = None
        run.updated_at = datetime.now(UTC)
        session.add(run)
        session.commit()


@celery_app.task(name="worker.tasks.execute_s3_batch_setup")
def execute_s3_batch_setup(run_id: str) -> None:
    engine = get_engine()
    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        if not run:
            return
        graph = session.get(AgateGraph, run.graph_id)
        if not graph:
            run.status = "failed"
            run.error_message = "Graph not found"
            run.updated_at = datetime.now(UTC)
            session.add(run)
            session.commit()
            return

        run.status = "running"
        run.updated_at = datetime.now(UTC)
        session.add(run)
        session.commit()

        try:
            spec = GraphSpec.model_validate_json(graph.spec_json)
            params = _first_s3_input_params(spec)
            bucket = str(params.get("bucket") or "").strip()
            folder_path = str(params.get("folder_path") or "").strip()
            if not bucket:
                raise ValueError(
                    "S3Input requires a non-empty bucket parameter before running the flow."
                )
            max_files = s3_max_files_from_params(params)
            prefix = folder_path.rstrip("/") + "/" if folder_path else ""

            overlay = merge_project_and_org_llm_api_keys(session, graph.project_id)
            with _env_overlay(overlay):
                s3_client = _s3_client_from_env()
                keys = list_json_keys_under_prefix(s3_client, bucket=bucket, prefix=prefix)

            skipped_invalid = 0
            skipped_cap = 0
            pending_ids: list[int] = []

            if not keys:
                run = session.get(AgateRun, run_id)
                if run:
                    run.status = "failed"
                    run.error_message = f"No JSON objects found under s3://{bucket}/{prefix or ''}"
                    run.result_json = json.dumps(
                        {
                            "s3_batch": {
                                "total_json_objects": 0,
                                "skipped_invalid": 0,
                                "skipped_cap": 0,
                                "valid_executed": 0,
                            }
                        }
                    )
                    run.updated_at = datetime.now(UTC)
                    session.add(run)
                    session.commit()
                return

            with _env_overlay(overlay):
                s3_client = _s3_client_from_env()
                for key in keys:
                    try:
                        response = s3_client.get_object(Bucket=bucket, Key=key)
                        raw = response["Body"].read().decode("utf-8")
                    except Exception as exc:  # noqa: BLE001 — classify as skipped row
                        row = AgateProcessedItem(
                            run_id=run_id,
                            source_file=key,
                            input_json=None,
                            status="skipped",
                            error_message=str(exc),
                        )
                        session.add(row)
                        skipped_invalid += 1
                        continue

                    doc, err = parse_s3_text_json_document(raw)
                    if err or doc is None:
                        row = AgateProcessedItem(
                            run_id=run_id,
                            source_file=key,
                            input_json=None,
                            status="skipped",
                            error_message=err or "invalid",
                        )
                        session.add(row)
                        skipped_invalid += 1
                        continue

                    if len(pending_ids) >= max_files:
                        row = AgateProcessedItem(
                            run_id=run_id,
                            source_file=key,
                            input_json=json.dumps(doc),
                            status="skipped",
                            error_message="max_files cap",
                        )
                        session.add(row)
                        skipped_cap += 1
                        continue

                    row = AgateProcessedItem(
                        run_id=run_id,
                        source_file=key,
                        input_json=json.dumps(doc),
                        status="pending",
                    )
                    session.add(row)
                    session.flush()
                    if row.id is not None:
                        pending_ids.append(row.id)

            batch_meta = {
                "total_json_objects": len(keys),
                "skipped_invalid": skipped_invalid,
                "skipped_cap": skipped_cap,
                "valid_executed": len(pending_ids),
            }
            run = session.get(AgateRun, run_id)
            if not run:
                return
            run.result_json = json.dumps({"s3_batch": batch_meta})
            run.updated_at = datetime.now(UTC)
            session.add(run)
            session.commit()

            if not pending_ids:
                run = session.get(AgateRun, run_id)
                if run:
                    run.status = "failed"
                    run.error_message = (
                        "No valid JSON files with a non-empty top-level "
                        "'text' field under the prefix."
                    )
                    run.updated_at = datetime.now(UTC)
                    session.add(run)
                    session.commit()
                return

            # Queue all ``execute_processed_item`` tasks and return immediately. A ``chord``
            # callback finalizes the parent run when every child finishes — unlike
            # ``group().get()`` inside this task, that does not pin a worker slot while children
            # are waiting to start (avoids deadlock at concurrency=1).
            logger.info(
                "execute_s3_batch_setup: queueing chord of %d execute_processed_item task(s) "
                "for run %s",
                len(pending_ids),
                run_id,
            )
            header = group(execute_processed_item.s(item_id) for item_id in pending_ids)
            _queue = os.environ.get("CELERY_QUEUE", "agate")
            # Use the two-argument ``chord(header, body)`` primitive + ``apply_async()`` so the
            # group is published to the broker in production. The ``header(body)`` callable form
            # can return an eager result object (no ``apply_async``) when ``task_always_eager``.
            chord(header, finalize_s3_parent_run.s(run_id)).apply_async(queue=_queue)
        except Exception as e:
            logger.exception("S3 batch setup failed for run %s", run_id)
            with Session(engine) as session3:
                run_fail = session3.get(AgateRun, run_id)
                if run_fail:
                    run_fail.status = "failed"
                    run_fail.error_message = str(e)
                    run_fail.updated_at = datetime.now(UTC)
                    session3.add(run_fail)
                    session3.commit()


@celery_app.task(name="worker.tasks.execute_processed_item")
def execute_processed_item(item_id: int) -> None:
    engine = get_engine()
    with Session(engine) as session:
        item = session.get(AgateProcessedItem, item_id)
        if not item or item.status != "pending":
            return
        item.status = "running"
        item.updated_at = datetime.now(UTC)
        session.add(item)
        session.commit()

    with Session(engine) as session:
        item = session.get(AgateProcessedItem, item_id)
        if not item:
            return
        run = session.get(AgateRun, item.run_id)
        if not run:
            item.status = "failed"
            item.error_message = "Parent run not found"
            item.updated_at = datetime.now(UTC)
            session.add(item)
            session.commit()
            return
        graph = session.get(AgateGraph, run.graph_id)
        if not graph:
            item.status = "failed"
            item.error_message = "Graph not found"
            item.updated_at = datetime.now(UTC)
            session.add(item)
            session.commit()
            return
        spec = GraphSpec.model_validate_json(graph.spec_json)

        batch_meta: dict[str, Any] = {}
        if run.result_json:
            try:
                wrap = json.loads(run.result_json)
                batch_meta = wrap.get("s3_batch") or {}
            except json.JSONDecodeError:
                batch_meta = {}

        input_json = item.input_json or "{}"
        source_file = item.source_file

        def s3_input_shim(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
            del params, inputs
            doc = json.loads(input_json)
            if not isinstance(doc, dict):
                raise ValueError("S3 batch item JSON must be a JSON object.")
            base = json_input_output_from_dict(doc)
            total = int(batch_meta.get("total_json_objects", 1))
            sk = int(batch_meta.get("skipped_invalid", 0)) + int(batch_meta.get("skipped_cap", 0))
            out = dict(base)
            out["total_files"] = total
            out["processed_files"] = 1
            out["skipped_files"] = sk
            out["source_file"] = source_file
            out["runs_created"] = []
            return out

        overlay = merge_project_and_org_llm_api_keys(session, graph.project_id)
        node_runners = dict(NODE_RUNNERS)
        node_runners["S3Input"] = s3_input_shim
        node_runners["DBOutput"] = run_db_output

        try:
            track_tok = attach_llm_tracking_context(
                LlmAttemptTrackingContext(
                    session=session,
                    project_id=graph.project_id,
                    run_id=run.id,
                    processed_item_id=item.id,
                )
            )
            try:
                with _env_overlay(overlay), _run_execution_env(
                    project_id=graph.project_id,
                    graph_id=graph.id,
                    run_id=run.id,
                ):
                    outputs = execute_graph(
                        spec,
                        node_runners=node_runners,
                        before_each_node=lambda nid, ntype: set_llm_tracking_current_node(
                            nid, ntype
                        ),
                    )
            finally:
                reset_llm_tracking_context(track_tok)
            item.status = "succeeded"
            item.result_json = json.dumps(outputs)
            item.error_message = None
        except Exception as e:
            item.status = "failed"
            item.error_message = str(e)
            item.result_json = None
        item.updated_at = datetime.now(UTC)
        session.add(item)
        session.commit()


@celery_app.task(name="worker.tasks.finalize_s3_parent_run")
def finalize_s3_parent_run(header_results: list[Any], run_id: str) -> None:
    """Chord body: aggregate parent ``agate_run`` after all ``execute_processed_item`` tasks."""
    del header_results  # each child returns None; status lives on ``agate_processed_item`` rows
    engine = get_engine()
    with Session(engine) as session:
        _finalize_s3_parent_run(session, run_id)
