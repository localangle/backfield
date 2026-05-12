"""Celery tasks."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
from agate_runtime import GraphSpec, execute_graph
from agate_runtime.nodes import NODE_RUNNERS
from agate_runtime.nodes.json_input import json_input_output_from_dict
from agate_runtime.s3_batch import (
    list_json_keys_under_prefix,
    parse_s3_text_json_document,
    s3_max_files_from_params,
)
from backfield_ai.credentials import merge_project_and_org_llm_api_keys
from backfield_ai.tracking_context import (
    LlmAttemptTrackingContext,
    attach_llm_tracking_context,
    reset_llm_tracking_context,
    set_llm_tracking_current_node,
)
from backfield_db import AgateGraph, AgateProcessedItem, AgateRun, StylebookBundleJob
from backfield_db.session import get_engine
from backfield_stylebook.full_bundle import export_stylebook_bundle, import_stylebook_bundle
from celery import Celery, chord, group
from sqlmodel import Session, select

from worker.nodes.db_output import run_db_output

logger = logging.getLogger(__name__)

# Must match ``apps/agate-api`` cancel handler so workers stop after ``POST /runs/{id}/cancel``.
_RUN_CANCELLED_MESSAGE = "Run cancelled by user"

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

        if run.status != "pending":
            return

        run.status = "running"
        session.add(run)
        session.commit()

        run = session.get(AgateRun, run_id)
        if not run or run.status != "running":
            return

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
            run = session.get(AgateRun, run_id)
            if not run or run.status != "running":
                return
            run.status = "succeeded"
            run.result_json = json.dumps(outputs)
            run.error_message = None
        except Exception as e:
            run = session.get(AgateRun, run_id)
            if run is None:
                return
            if run.error_message == _RUN_CANCELLED_MESSAGE:
                return
            run.status = "failed"
            run.error_message = str(e)
            run.result_json = None
        run = session.get(AgateRun, run_id)
        if run is None:
            return
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

        if run.status != "pending":
            return

        run.status = "running"
        run.updated_at = datetime.now(UTC)
        session.add(run)
        session.commit()

        run = session.get(AgateRun, run_id)
        if not run or run.status != "running":
            return

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
        if item.status != "running":
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


def _stylebook_bundle_bucket_prefix() -> tuple[str, str]:
    bucket = os.environ.get("STYLEBOOK_BUNDLE_S3_BUCKET", "").strip()
    prefix = os.environ.get("STYLEBOOK_BUNDLE_S3_PREFIX", "stylebook-bundles").strip().strip("/")
    if not bucket:
        raise ValueError(
            "STYLEBOOK_BUNDLE_S3_BUCKET must be set to export or import stylebook bundles."
        )
    return bucket, prefix


def _s3_client_stylebook_bundles() -> Any:
    aws_access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    aws_secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    aws_session_token = os.environ.get("AWS_SESSION_TOKEN")
    if not aws_access_key or not aws_secret_key:
        raise ValueError(
            "AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY must be set for stylebook bundle staging."
        )
    session_kwargs: dict[str, str] = {
        "aws_access_key_id": aws_access_key,
        "aws_secret_access_key": aws_secret_key,
    }
    if aws_session_token:
        session_kwargs["aws_session_token"] = aws_session_token
    endpoint = os.environ.get("AWS_S3_ENDPOINT_URL") or os.environ.get("AWS_ENDPOINT_URL")
    if endpoint:
        return boto3.client("s3", endpoint_url=endpoint, **session_kwargs)
    return boto3.client("s3", **session_kwargs)


def _fail_stylebook_bundle_job(engine: Any, job_id: str, message: str) -> None:
    with Session(engine) as session:
        job = session.get(StylebookBundleJob, job_id)
        if job is None:
            return
        job.status = "failed"
        job.error_message = message[:10000]
        job.updated_at = datetime.now(UTC)
        session.add(job)
        session.commit()


def _update_bundle_job_progress(engine: Any, job_id: str, payload: dict[str, Any]) -> None:
    with Session(engine) as session:
        job = session.get(StylebookBundleJob, job_id)
        if job is None:
            return
        base: dict[str, Any] = {}
        if isinstance(job.progress_json, dict):
            base = dict(job.progress_json)
        base["latest"] = payload
        job.progress_json = base
        job.updated_at = datetime.now(UTC)
        session.add(job)
        session.commit()


@celery_app.task(name="worker.tasks.export_stylebook_bundle")
def export_stylebook_bundle_task(job_id: str) -> None:
    """Build a stylebook ZIP bundle and upload it to the configured staging bucket."""
    engine = get_engine()
    try:
        _stylebook_bundle_bucket_prefix()
    except ValueError as e:
        _fail_stylebook_bundle_job(engine, job_id, str(e))
        return

    with Session(engine) as session:
        job = session.get(StylebookBundleJob, job_id)
        if job is None:
            return
        if job.kind != "export":
            return
        if job.status != "queued":
            return
        org_id = int(job.organization_id)
        sb_id = job.source_stylebook_id
        if sb_id is None:
            job.status = "failed"
            job.error_message = "export job missing source_stylebook_id"
            job.updated_at = datetime.now(UTC)
            session.add(job)
            session.commit()
            return
        bucket = job.s3_bucket
        key = job.s3_key
        if not bucket or not key:
            job.status = "failed"
            job.error_message = "export job missing s3_bucket or s3_key"
            job.updated_at = datetime.now(UTC)
            session.add(job)
            session.commit()
            return
        job.status = "running"
        job.updated_at = datetime.now(UTC)
        session.add(job)
        session.commit()

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
            tmp_path = tf.name
        assert tmp_path is not None
        with Session(engine) as session:
            manifest = export_stylebook_bundle(
                session,
                organization_id=org_id,
                stylebook_id=int(sb_id),
                zip_path=tmp_path,
                on_progress=lambda p: _update_bundle_job_progress(engine, job_id, p),
            )
        client = _s3_client_stylebook_bundles()
        client.upload_file(
            tmp_path,
            bucket,
            key,
            ExtraArgs={"ContentType": "application/zip"},
        )
        with Session(engine) as session:
            job2 = session.get(StylebookBundleJob, job_id)
            if job2 is None:
                return
            job2.status = "succeeded"
            job2.progress_json = {
                "manifest": {
                    "source_stylebook": manifest.get("source_stylebook"),
                    "project_slices": manifest.get("project_slices"),
                    "file_count": len(manifest.get("files", [])),
                }
            }
            job2.error_message = None
            job2.updated_at = datetime.now(UTC)
            session.add(job2)
            session.commit()
    except Exception as e:
        logger.exception("export_stylebook_bundle_task failed")
        _fail_stylebook_bundle_job(engine, job_id, str(e))
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


@celery_app.task(name="worker.tasks.import_stylebook_bundle")
def import_stylebook_bundle_task(job_id: str) -> None:
    """Download a staged ZIP from S3 and import it into a new stylebook."""
    engine = get_engine()
    try:
        _stylebook_bundle_bucket_prefix()
    except ValueError as e:
        _fail_stylebook_bundle_job(engine, job_id, str(e))
        return

    with Session(engine) as session:
        job = session.get(StylebookBundleJob, job_id)
        if job is None:
            return
        if job.kind != "import":
            return
        if job.status != "queued":
            return
        bucket = job.s3_bucket
        key = job.s3_key
        if not bucket or not key:
            _fail_stylebook_bundle_job(engine, job_id, "import job missing s3_bucket or s3_key")
            return
        req = job.import_request_json or {}
        name = req.get("new_stylebook_name") or req.get("name")
        if not name or not str(name).strip():
            _fail_stylebook_bundle_job(engine, job_id, "import job missing new_stylebook_name")
            return
        job.status = "running"
        job.updated_at = datetime.now(UTC)
        session.add(job)
        session.commit()
        org_id = int(job.organization_id)

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
            tmp_path = tf.name
        assert tmp_path is not None
        client = _s3_client_stylebook_bundles()
        client.download_file(bucket, key, tmp_path)
        with Session(engine) as session:
            new_book, stats = import_stylebook_bundle(
                session,
                organization_id=org_id,
                zip_path=tmp_path,
                new_stylebook_name=str(name).strip(),
                on_progress=lambda p: _update_bundle_job_progress(engine, job_id, p),
            )
            jid = new_book.id  # type: ignore[union-attr]
            new_sb_id = int(jid)  # type: ignore[arg-type]
            job2 = session.get(StylebookBundleJob, job_id)
            if job2 is None:
                return
            job2.status = "succeeded"
            job2.result_stylebook_id = new_sb_id
            job2.progress_json = stats
            job2.error_message = None
            job2.updated_at = datetime.now(UTC)
            session.add(job2)
            session.commit()
    except Exception as e:
        logger.exception("import_stylebook_bundle_task failed")
        _fail_stylebook_bundle_job(engine, job_id, str(e))
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
