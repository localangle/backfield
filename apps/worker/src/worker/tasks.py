"""Celery tasks."""

from __future__ import annotations

import contextvars
import json
import logging
import os
import tempfile
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
from agate_nodes.s3_output.node import (
    normalize_s3_output_bucket,
    s3_output_payloads_in_run_output,
    upload_s3_output_body,
)
from agate_runtime import GraphSpec, execute_graph
from agate_runtime.nodes import NODE_RUNNERS
from agate_runtime.nodes.json_input import json_input_output_from_dict
from agate_runtime.run_graph_spec import (
    GRAPH_SPEC_JSON_KEY,
    merge_run_result_payload,
    parse_run_result_payload,
    resolve_run_graph_spec_json,
)
from agate_runtime.s3_batch import (
    list_json_keys_under_prefix,
    parse_s3_text_json_document,
    s3_max_files_from_params,
)
from agate_utils.llm import call_llm
from backfield_ai.credentials import merge_project_and_org_llm_api_keys
from backfield_ai.tracking_context import (
    LlmAttemptTrackingContext,
    attach_llm_tracking_context,
    reset_llm_tracking_context,
    set_llm_tracking_current_node,
)
from backfield_db import (
    AgateGraph,
    AgateNodeTiming,
    AgateProcessedItem,
    AgateRun,
    BackfieldProject,
    Stylebook,
    StylebookBundleJob,
    StylebookCandidateAiReview,
    StylebookCleanupAiReview,
    StylebookCleanupCheckRun,
)
from backfield_db.session import get_engine
from backfield_entities.catalog.candidate_ai_review import list_open_candidate_ids_for_review
from backfield_entities.catalog.full_bundle import export_stylebook_bundle, import_stylebook_bundle
from backfield_entities.ingest.semantic_indexing.reindex_contract import SemanticReindexScope
from backfield_entities.processed_item_article_link import (
    resolve_substrate_article_id_for_processed_item,
)
from backfield_entities.quality.check_runs import (
    CleanupRunScope,
    build_cleanup_check_items,
    persist_cleanup_check_results,
)
from backfield_entities.quality.finders._duplicate_labels import DEFAULT_FULL_SIMILARITY_THRESHOLD
from backfield_entities.quality.finders.duplicate_locations import (
    DEFAULT_FULL_SIMILARITY_THRESHOLD as LOCATION_FULL_THRESHOLD,
)
from backfield_entities.quality.finders.duplicate_locations import (
    DEFAULT_HEAD_SIMILARITY_THRESHOLD as LOCATION_HEAD_THRESHOLD,
)
from backfield_entities.quality.finders.duplicate_locations import (
    duplicate_location_cluster_ids,
)
from backfield_entities.quality.finders.duplicate_organizations import (
    duplicate_organization_cluster_ids,
)
from backfield_entities.quality.finders.duplicate_people import duplicate_person_cluster_ids
from celery import Celery, chord, group
from celery.exceptions import Reject
from sqlalchemy import delete
from sqlmodel import Session, select

from worker.flags.replace_geography import clear_replace_article_geography_flags
from worker.nodes.db_output import run_db_output
from worker.processed_item_claims import (
    active_execute_processed_item_ids,
    release_orphan_running_items_for_run,
    release_running_claim,
    should_reconcile_orphan_running_items,
)
from worker.semantic_indexing.reindex import run_semantic_reindex_for_scope
from worker.substrate.candidates.ai_review import run_candidate_ai_review
from worker.substrate.cleanup.ai_review import (
    load_cluster_members,
    run_cleanup_review_clusters,
)

logger = logging.getLogger(__name__)


def _graph_has_db_output(spec: GraphSpec) -> bool:
    return any(node.type == "DBOutput" for node in spec.nodes)

# Must match ``apps/agate-api`` cancel handler so workers stop after ``POST /runs/{id}/cancel``.
_RUN_CANCELLED_MESSAGE = "Run cancelled by user"

_TASK_SOFT_TIME_LIMIT = int(os.getenv("TASK_SOFT_TIME_LIMIT", "3600"))
_TASK_HARD_TIME_LIMIT = int(os.getenv("TASK_HARD_TIME_LIMIT", "4200"))
_STALE_RUNNING_GRACE_S = int(os.getenv("TASK_STALE_RUNNING_GRACE_S", "300"))
_STALE_RUNNING_AFTER_S = _TASK_HARD_TIME_LIMIT + _STALE_RUNNING_GRACE_S
_STALE_RUNNING_MESSAGE = "Processing interrupted (worker lost or exceeded time limit)"

_current_processed_item_id: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "current_processed_item_id",
    default=None,
)


def _running_item_touch_ts(item: AgateProcessedItem) -> datetime:
    return item.started_at or item.updated_at or item.created_at


def _is_stale_running_item(item: AgateProcessedItem, *, now: datetime | None = None) -> bool:
    if item.status != "running":
        return False
    now = now or datetime.now(UTC)
    touch = _running_item_touch_ts(item)
    if touch.tzinfo is None:
        touch = touch.replace(tzinfo=UTC)
    return (now - touch).total_seconds() > _STALE_RUNNING_AFTER_S


def _reap_stale_running_items(
    session: Session,
    items: list[AgateProcessedItem],
    *,
    now: datetime | None = None,
) -> None:
    """Mark zombie ``running`` rows terminal so batch runs can finalize after worker loss."""
    now = now or datetime.now(UTC)
    for row in items:
        if not _is_stale_running_item(row, now=now):
            continue
        row.status = "failed"
        row.error_message = _STALE_RUNNING_MESSAGE
        row.updated_at = now
        session.add(row)


def _reap_stale_running_items_for_run(
    session: Session,
    run_id: str,
    *,
    now: datetime | None = None,
) -> int:
    """Reap stale ``running`` rows for one parent run (batch progress helper)."""
    now = now or datetime.now(UTC)
    rows = list(
        session.exec(
            select(AgateProcessedItem).where(
                AgateProcessedItem.run_id == run_id,
                AgateProcessedItem.status == "running",
            )
        ).all()
    )
    stale_rows = [row for row in rows if _is_stale_running_item(row, now=now)]
    if not stale_rows:
        return 0
    _reap_stale_running_items(session, stale_rows, now=now)
    return len(stale_rows)


def _item_blocks_run_finalization(item: AgateProcessedItem) -> bool:
    if item.status == "pending":
        return True
    return item.status == "running" and not _is_stale_running_item(item)


def _try_claim_processed_item(
    session: Session,
    item: AgateProcessedItem,
    *,
    allow_running_reclaim: bool = False,
) -> bool:
    if item.status == "pending":
        item.status = "running"
        item.started_at = datetime.now(UTC)
        item.updated_at = datetime.now(UTC)
        session.add(item)
        return True
    if item.status == "running" and (
        _is_stale_running_item(item) or allow_running_reclaim
    ):
        logger.warning(
            "Reclaiming running processed_item id=%s run_id=%s redelivered=%s stale=%s",
            item.id,
            item.run_id,
            allow_running_reclaim,
            _is_stale_running_item(item),
        )
        item.started_at = datetime.now(UTC)
        item.updated_at = datetime.now(UTC)
        item.error_message = None
        session.add(item)
        return True
    return False


def _task_is_redelivered() -> bool:
    try:
        from celery import current_task

        return bool(current_task.request.delivery_info.get("redelivered"))
    except Exception:
        return False


def _node_wall_clock_hooks() -> tuple[
    Callable[[str, str], None],
    Callable[[str, str, float], None],
    dict[str, float],
]:
    """Return before/after hooks and a mutable timing map for execute_graph."""
    timings: dict[str, float] = {}

    def before(node_id: str, node_type: str) -> None:
        set_llm_tracking_current_node(node_id, node_type)

    def after(node_id: str, node_type: str, elapsed_s: float) -> None:
        timings[f"{node_type}:{node_id}"] = elapsed_s

    return before, after, timings


def _log_node_wall_clock_summary(
    *,
    run_id: str,
    processed_item_id: int | None,
    timings: dict[str, float],
    session: Session | None = None,
) -> None:
    if not timings:
        return
    total_s = sum(timings.values())
    top = sorted(timings.items(), key=lambda item: item[1], reverse=True)[:8]
    summary = ", ".join(f"{key}={secs:.1f}s" for key, secs in top)
    logger.info(
        "Node wall-clock run_id=%s processed_item_id=%s total_s=%.1f top=%s",
        run_id,
        processed_item_id,
        total_s,
        summary,
    )
    if session is None or processed_item_id is None:
        return
    session.exec(
        delete(AgateNodeTiming).where(
            AgateNodeTiming.processed_item_id == int(processed_item_id)
        )
    )
    for key, elapsed_s in timings.items():
        node_type, _, node_id = key.partition(":")
        session.add(
            AgateNodeTiming(
                run_id=run_id,
                processed_item_id=int(processed_item_id),
                node_id=node_id or key,
                node_type=node_type or "unknown",
                elapsed_s=float(elapsed_s),
            )
        )


celery_app = Celery(
    "agate_worker",
    broker=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
)
celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True


def _register_worker_process_hooks() -> None:
    from celery.signals import (
        task_failure,
        worker_init,
        worker_process_init,
        worker_process_shutdown,
    )

    from worker.startup import prepare_worker_parent_for_fork, warm_worker_process

    # weak=False is required: Celery signals hold receivers via weakref by default, and these
    # closures have no other strong reference, so they would be garbage-collected immediately.

    @worker_init.connect(weak=False)
    def _freeze_parent_heap_before_fork(**_kwargs: Any) -> None:
        prepare_worker_parent_for_fork()

    @worker_process_init.connect(weak=False)
    def _warm_celery_child_process(**_kwargs: Any) -> None:
        warm_worker_process()

    @worker_process_shutdown.connect(weak=False)
    def _release_claim_on_child_shutdown(**_kwargs: Any) -> None:
        item_id = _current_processed_item_id.get()
        if item_id is None:
            return
        try:
            engine = get_engine()
            with Session(engine) as session:
                if release_running_claim(session, int(item_id)):
                    session.commit()
                    logger.warning(
                        "Released running processed_item id=%s to pending on worker child shutdown",
                        item_id,
                    )
        except Exception:
            logger.exception(
                "Failed to release processed_item claim on worker shutdown item_id=%s",
                item_id,
            )

    @task_failure.connect(weak=False)
    def _release_claim_on_task_failure(
        sender: object | None = None,
        args: tuple[Any, ...] | None = None,
        **_kwargs: Any,
    ) -> None:
        if getattr(sender, "name", None) != "worker.tasks.execute_processed_item":
            return
        if not args:
            return
        try:
            item_id = int(args[0])
        except (TypeError, ValueError):
            return
        try:
            engine = get_engine()
            with Session(engine) as session:
                if release_running_claim(session, item_id):
                    session.commit()
                    logger.warning(
                        "Released running processed_item id=%s to pending after task failure",
                        item_id,
                    )
        except Exception:
            logger.exception(
                "Failed to release processed_item claim after task failure item_id=%s",
                item_id,
            )


_register_worker_process_hooks()


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


def _call_llm_with_env_api_keys(prompt: str, **kwargs: Any) -> str:
    """Pass org/project API keys explicitly; ``call_llm`` does not read env by default."""
    return call_llm(
        prompt,
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        azure_api_key=os.getenv("AZURE_API_KEY"),
        azure_api_base=os.getenv("AZURE_API_BASE"),
        **kwargs,
    )


def _project_system_prompt_from_settings(settings_json: str | None) -> str | None:
    if not settings_json:
        return None
    try:
        data = json.loads(settings_json)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("system_prompt")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _load_project_system_prompt(session: Session, project_id: int) -> str | None:
    project = session.get(BackfieldProject, int(project_id))
    if project is None:
        return None
    return _project_system_prompt_from_settings(project.settings_json)


@contextmanager
def _run_execution_env(
    *,
    project_id: int,
    graph_id: str,
    run_id: str,
    replace_article_geography: bool = False,
    processed_item_id: int | None = None,
    project_system_prompt: str | None = None,
):
    updates: dict[str, str] = {
        "BACKFIELD_PROJECT_ID": str(project_id),
        "BACKFIELD_GRAPH_ID": str(graph_id),
        "BACKFIELD_RUN_ID": str(run_id),
    }
    if replace_article_geography:
        updates["BACKFIELD_REPLACE_ARTICLE_GEOGRAPHY"] = "1"
    if processed_item_id is not None:
        updates["BACKFIELD_PROCESSED_ITEM_ID"] = str(int(processed_item_id))
    if project_system_prompt:
        updates["BACKFIELD_PROJECT_SYSTEM_PROMPT"] = project_system_prompt
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
    _reap_stale_running_items(session, items)
    session.commit()
    items = list(
        session.exec(select(AgateProcessedItem).where(AgateProcessedItem.run_id == run_id)).all()
    )
    if any(_item_blocks_run_finalization(row) for row in items):
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

    project_id: int
    graph_id: str
    overlay: dict[str, str]
    spec: GraphSpec
    replace_geography: bool
    project_system_prompt: str | None

    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        if not run or run.status != "running":
            return
        graph = session.get(AgateGraph, run.graph_id)
        if not graph:
            return
        spec = GraphSpec.model_validate_json(
            resolve_run_graph_spec_json(
                run_result_json=run.result_json,
                graph_spec_json=graph.spec_json,
            )
        )
        overlay = merge_project_and_org_llm_api_keys(session, graph.project_id)
        replace_geography = bool(run.replace_article_geography_on_persist)
        project_system_prompt = _load_project_system_prompt(session, graph.project_id)
        project_id = int(graph.project_id)
        graph_id = str(graph.id)
        session.commit()

    node_runners = dict(NODE_RUNNERS)
    node_runners["DBOutput"] = run_db_output
    outputs: dict[str, Any] | None = None
    node_timings: dict[str, float] = {}
    run_error: str | None = None

    track_tok = attach_llm_tracking_context(
        LlmAttemptTrackingContext(
            project_id=project_id,
            run_id=run_id,
        )
    )
    try:
        with _env_overlay(overlay), _run_execution_env(
            project_id=project_id,
            graph_id=graph_id,
            run_id=run_id,
            replace_article_geography=replace_geography,
            project_system_prompt=project_system_prompt,
        ):
            before_node, after_node, node_timings = _node_wall_clock_hooks()
            outputs = execute_graph(
                spec,
                node_runners=node_runners,
                before_each_node=before_node,
                after_each_node=after_node,
            )
            _log_node_wall_clock_summary(
                run_id=run_id,
                processed_item_id=None,
                timings=node_timings,
            )
    except Exception as e:
        run_error = str(e)
    finally:
        reset_llm_tracking_context(track_tok)

    with Session(engine) as session:
        run = session.get(AgateRun, run_id)
        if not run or run.status != "running":
            return
        try:
            if run_error is not None:
                if run.error_message == _RUN_CANCELLED_MESSAGE:
                    return
                run.status = "failed"
                run.error_message = run_error
                run.result_json = None
            else:
                if replace_geography and not _graph_has_db_output(spec) and run.id is not None:
                    clear_replace_article_geography_flags(session, run_id=str(run.id))
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
            spec_json = resolve_run_graph_spec_json(
                run_result_json=run.result_json,
                graph_spec_json=graph.spec_json,
            )
            spec = GraphSpec.model_validate_json(spec_json)
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
            pending: list[tuple[int, int]] = []

            if not keys:
                run = session.get(AgateRun, run_id)
                if run:
                    run.status = "failed"
                    run.error_message = f"No JSON objects found under s3://{bucket}/{prefix or ''}"
                    run.result_json = merge_run_result_payload(
                        run.result_json,
                        s3_batch={
                            "total_json_objects": 0,
                            "skipped_invalid": 0,
                            "skipped_cap": 0,
                            "valid_executed": 0,
                        },
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

                    if len(pending) >= max_files:
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
                        text_len = len(str(doc.get("text") or ""))
                        pending.append((int(row.id), text_len))

            batch_meta = {
                "total_json_objects": len(keys),
                "skipped_invalid": skipped_invalid,
                "skipped_cap": skipped_cap,
                "valid_executed": len(pending),
            }
            run = session.get(AgateRun, run_id)
            if not run:
                return
            run.result_json = merge_run_result_payload(
                run.result_json,
                s3_batch=batch_meta,
                graph_spec_json=spec_json,
            )
            run.updated_at = datetime.now(UTC)
            session.add(run)
            session.commit()

            if not pending:
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
                len(pending),
                run_id,
            )
            pending_sorted = sorted(pending, key=lambda row: row[1], reverse=True)
            ordered_ids = [item_id for item_id, _ in pending_sorted]
            header = group(execute_processed_item.s(item_id) for item_id in ordered_ids)
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


@celery_app.task(name="worker.tasks.execute_run_replay_setup")
def execute_run_replay_setup(source_run_id: str, new_run_id: str) -> None:
    """Clone replayable processed items from a source run and re-queue them on a new run."""
    engine = get_engine()
    with Session(engine) as session:
        source = session.get(AgateRun, source_run_id)
        new_run = session.get(AgateRun, new_run_id)
        if source is None or new_run is None:
            return
        if new_run.status != "pending":
            return

        source_items = list(
            session.exec(
                select(AgateProcessedItem)
                .where(AgateProcessedItem.run_id == source_run_id)
                .order_by(AgateProcessedItem.id)
            ).all()
        )
        replay_rows = [
            row
            for row in source_items
            if row.input_json and (row.status or "").strip().lower() != "skipped"
        ]
        if not replay_rows:
            new_run.status = "failed"
            new_run.error_message = "No replayable items found on the source run."
            new_run.updated_at = datetime.now(UTC)
            session.add(new_run)
            session.commit()
            return

        source_payload = parse_run_result_payload(source.result_json)
        merge_updates: dict[str, Any] = {}
        s3_batch = source_payload.get("s3_batch")
        if isinstance(s3_batch, dict):
            merge_updates["s3_batch"] = s3_batch
        snap = source_payload.get(GRAPH_SPEC_JSON_KEY)
        if isinstance(snap, str) and snap.strip():
            merge_updates[GRAPH_SPEC_JSON_KEY] = snap

        new_run.status = "running"
        new_run.updated_at = datetime.now(UTC)
        new_run.result_json = merge_run_result_payload(new_run.result_json, **merge_updates)
        session.add(new_run)

        pending_ids: list[int] = []
        for row in replay_rows:
            clone = AgateProcessedItem(
                run_id=new_run_id,
                source_file=row.source_file,
                input_json=row.input_json,
                status="pending",
            )
            session.add(clone)
            session.flush()
            if clone.id is not None:
                pending_ids.append(int(clone.id))

        session.commit()

        if not pending_ids:
            new_run_fail = session.get(AgateRun, new_run_id)
            if new_run_fail is not None:
                new_run_fail.status = "failed"
                new_run_fail.error_message = "Replay setup produced no processed items."
                new_run_fail.updated_at = datetime.now(UTC)
                session.add(new_run_fail)
                session.commit()
            return

        logger.info(
            "execute_run_replay_setup: queueing chord of %d execute_processed_item task(s) "
            "for replay run %s (source %s)",
            len(pending_ids),
            new_run_id,
            source_run_id,
        )
        _queue = os.environ.get("CELERY_QUEUE", "agate")
        header = group(execute_processed_item.s(item_id) for item_id in pending_ids)
        chord(header, finalize_s3_parent_run.s(new_run_id)).apply_async(queue=_queue)


@celery_app.task(
    name="worker.tasks.execute_processed_item",
    soft_time_limit=_TASK_SOFT_TIME_LIMIT,
    time_limit=_TASK_HARD_TIME_LIMIT,
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_processed_item(item_id: int) -> None:
    token = _current_processed_item_id.set(int(item_id))
    try:
        _execute_processed_item_impl(item_id)
    finally:
        _current_processed_item_id.reset(token)


def _execute_processed_item_impl(item_id: int) -> None:
    engine = get_engine()
    with Session(engine) as session:
        item = session.get(AgateProcessedItem, item_id)
        if not item:
            return
        reaped = _reap_stale_running_items_for_run(session, item.run_id)
        running_rows = list(
            session.exec(
                select(AgateProcessedItem).where(
                    AgateProcessedItem.run_id == item.run_id,
                    AgateProcessedItem.status == "running",
                )
            ).all()
        )
        released = 0
        if should_reconcile_orphan_running_items(len(running_rows), run_id=item.run_id):
            active_ids = active_execute_processed_item_ids(celery_app) | {int(item_id)}
            released = release_orphan_running_items_for_run(
                session,
                item.run_id,
                active_item_ids=active_ids,
            )
        if reaped or released:
            logger.info(
                "Reconciled running processed_item rows for run_id=%s "
                "(stale_reaped=%d orphan_released=%d)",
                item.run_id,
                reaped,
                released,
            )
            session.commit()
        if not _try_claim_processed_item(
            session,
            item,
            allow_running_reclaim=_task_is_redelivered(),
        ):
            if item.status == "running":
                # Worker loss can leave a zombie ``running`` row while the broker redelivers.
                # Requeue so the next attempt can reclaim once ``redelivered`` is set.
                raise Reject(requeue=True)
            return
        session.commit()

    project_id: int
    graph_id: str
    run_id_str: str
    overlay: dict[str, str]
    spec: GraphSpec
    node_runners: dict[str, Any]
    replace_geography: bool
    project_system_prompt: str | None
    iid: int | None
    has_db_output: bool

    try:
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
            spec = GraphSpec.model_validate_json(
                resolve_run_graph_spec_json(
                    run_result_json=run.result_json,
                    graph_spec_json=graph.spec_json,
                )
            )

            batch_meta: dict[str, Any] = {}
            if run.result_json:
                try:
                    wrap = json.loads(run.result_json)
                    batch_meta = wrap.get("s3_batch") or {}
                except json.JSONDecodeError:
                    batch_meta = {}

            input_json = item.input_json or "{}"
            source_file = item.source_file
            doc = json.loads(input_json)
            if not isinstance(doc, dict):
                raise ValueError("Processed item input_json must be a JSON object.")

            overlay = merge_project_and_org_llm_api_keys(session, graph.project_id)
            node_runners = dict(NODE_RUNNERS)
            node_runners["DBOutput"] = run_db_output
            ingress_types = {node.type for node in spec.nodes}
            if "S3Input" in ingress_types:

                def s3_input_shim(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
                    del params, inputs
                    base = json_input_output_from_dict(doc)
                    total = int(batch_meta.get("total_json_objects", 1))
                    sk = int(batch_meta.get("skipped_invalid", 0)) + int(
                        batch_meta.get("skipped_cap", 0)
                    )
                    out = dict(base)
                    out["total_files"] = total
                    out["processed_files"] = 1
                    out["skipped_files"] = sk
                    out["source_file"] = source_file
                    out["runs_created"] = []
                    return out

                node_runners["S3Input"] = s3_input_shim
            if "TextInput" in ingress_types:

                def text_input_shim(
                    params: dict[str, Any], inputs: dict[str, Any]
                ) -> dict[str, Any]:
                    del params, inputs
                    text = doc.get("text") or ""
                    if not str(text).strip():
                        raise ValueError(
                            "TextInput requires non-empty text. "
                            "Please add text to the TextInput node before running the flow."
                        )
                    return {"text": str(text)}

                node_runners["TextInput"] = text_input_shim
            if "JSONInput" in ingress_types:

                def json_input_shim(
                    params: dict[str, Any], inputs: dict[str, Any]
                ) -> dict[str, Any]:
                    del params, inputs
                    return json_input_output_from_dict(doc)

                node_runners["JSONInput"] = json_input_shim

            replace_geography = bool(
                item.replace_article_geography_on_persist
                or run.replace_article_geography_on_persist
            )
            project_system_prompt = _load_project_system_prompt(session, graph.project_id)
            project_id = int(graph.project_id)
            graph_id = str(graph.id)
            run_id_str = str(run.id)
            iid = int(item.id) if item.id is not None else None
            has_db_output = _graph_has_db_output(spec)
            session.commit()
    except Exception as e:
        with Session(engine) as session:
            item = session.get(AgateProcessedItem, item_id)
            if item:
                item.status = "failed"
                item.error_message = str(e)
                item.result_json = None
                item.substrate_article_id = None
                item.updated_at = datetime.now(UTC)
                session.add(item)
                session.commit()
                _finalize_s3_parent_run(session, item.run_id)
        return

    outputs: dict[str, Any] | None = None
    node_timings: dict[str, float] = {}
    item_error: str | None = None

    track_tok = attach_llm_tracking_context(
        LlmAttemptTrackingContext(
            project_id=project_id,
            run_id=run_id_str,
            processed_item_id=item_id,
        )
    )
    try:
        with _env_overlay(overlay), _run_execution_env(
            project_id=project_id,
            graph_id=graph_id,
            run_id=run_id_str,
            replace_article_geography=replace_geography,
            processed_item_id=iid,
            project_system_prompt=project_system_prompt,
        ):
            before_node, after_node, node_timings = _node_wall_clock_hooks()
            outputs = execute_graph(
                spec,
                node_runners=node_runners,
                before_each_node=before_node,
                after_each_node=after_node,
            )
    except Exception as e:
        item_error = str(e)
    finally:
        reset_llm_tracking_context(track_tok)

    with Session(engine) as session:
        item = session.get(AgateProcessedItem, item_id)
        if not item:
            return
        _log_node_wall_clock_summary(
            run_id=run_id_str,
            processed_item_id=iid,
            timings=node_timings,
            session=session,
        )
        if item_error is None:
            item.status = "succeeded"
            item.result_json = json.dumps(outputs)
            item.substrate_article_id = resolve_substrate_article_id_for_processed_item(
                outputs=outputs
            )
            item.error_message = None
        else:
            item.status = "failed"
            item.error_message = item_error
            item.result_json = None
            item.substrate_article_id = None
        if replace_geography and not has_db_output and run_id_str:
            clear_replace_article_geography_flags(
                session,
                run_id=run_id_str,
                processed_item_id=iid,
            )
        item.updated_at = datetime.now(UTC)
        session.add(item)
        session.commit()
        _finalize_s3_parent_run(session, item.run_id)


@celery_app.task(name="worker.tasks.finalize_s3_parent_run")
def finalize_s3_parent_run(header_results: list[Any], run_id: str) -> None:
    """Chord body: aggregate parent ``agate_run`` after all ``execute_processed_item`` tasks."""
    del header_results  # each child returns None; status lives on ``agate_processed_item`` rows
    engine = get_engine()
    with Session(engine) as session:
        _finalize_s3_parent_run(session, run_id)


def _s3_output_public_read_by_bucket(spec: GraphSpec) -> dict[str, bool]:
    """``public_read`` per S3Output bucket from graph node params (first node wins)."""
    out: dict[str, bool] = {}
    for node in spec.nodes:
        if node.type != "S3Output":
            continue
        bucket = normalize_s3_output_bucket(str(node.params.get("bucket") or ""))
        if bucket and bucket not in out:
            out[bucket] = bool(node.params.get("public_read"))
    return out


def _stamp_s3_sync_state(
    docs: list[dict[str, Any] | None],
    payload_keys: list[str],
    *,
    synced_at: str,
    error: str | None,
) -> None:
    """Record sync success/failure on each S3Output payload in run + reviewed JSON."""
    for doc in docs:
        if not isinstance(doc, dict):
            continue
        for key in payload_keys:
            target = doc.get(key)
            if not isinstance(target, dict):
                continue
            if error is None:
                target["s3_synced_at"] = synced_at
                target.pop("s3_sync_error", None)
            else:
                target["s3_sync_error"] = error


@celery_app.task(name="worker.tasks.sync_processed_item_s3_output")
def sync_processed_item_s3_output(item_id: int) -> None:
    """Overwrite the S3Output file(s) for one item with its current (reviewed) JSON.

    Uses ``reviewed_output_json`` when review edits exist, otherwise the original
    ``result_json``. The upload targets the same ``s3_bucket``/``s3_key`` recorded
    by the S3Output node at run time, and sync state is stamped back onto the
    item so the review UI can surface it.
    """
    engine = get_engine()
    with Session(engine) as session:
        item = session.get(AgateProcessedItem, item_id)
        if not item or not item.result_json:
            return
        run = session.get(AgateRun, item.run_id)
        if not run:
            return
        graph = session.get(AgateGraph, run.graph_id)
        if not graph:
            return

        try:
            output = json.loads(item.result_json)
        except json.JSONDecodeError:
            return
        if not isinstance(output, dict):
            return
        reviewed: dict[str, Any] | None = None
        if item.reviewed_output_json:
            try:
                parsed = json.loads(item.reviewed_output_json)
                reviewed = parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                reviewed = None

        source = reviewed if reviewed is not None else output
        payloads = s3_output_payloads_in_run_output(source)
        if not payloads:
            logger.info("S3 sync skipped for item %s: no S3 Output upload recorded", item_id)
            return

        spec = GraphSpec.model_validate_json(
            resolve_run_graph_spec_json(
                run_result_json=run.result_json,
                graph_spec_json=graph.spec_json,
            )
        )
        public_read_by_bucket = _s3_output_public_read_by_bucket(spec)
        overlay = merge_project_and_org_llm_api_keys(session, graph.project_id)

        error: str | None = None
        try:
            with _env_overlay(overlay):
                s3_client = _s3_client_from_env()
                for payload in payloads.values():
                    bucket = str(payload["s3_bucket"])
                    key = str(payload["s3_key"])
                    logger.info(
                        "S3 sync uploading item %s to s3://%s/%s", item_id, bucket, key
                    )
                    upload_s3_output_body(
                        s3_client,
                        bucket=bucket,
                        key=key,
                        body=payload["consolidated"],
                        public_read=public_read_by_bucket.get(bucket, False),
                    )
        except Exception as e:
            logger.exception("S3 sync failed for item %s", item_id)
            error = str(e)

        _stamp_s3_sync_state(
            [output, reviewed],
            list(payloads.keys()),
            synced_at=datetime.now(UTC).isoformat(),
            error=error,
        )
        item.result_json = json.dumps(output)
        item.substrate_article_id = resolve_substrate_article_id_for_processed_item(
            outputs=output
        )
        if reviewed is not None:
            item.reviewed_output_json = json.dumps(reviewed)
        item.updated_at = datetime.now(UTC)
        session.add(item)
        session.commit()


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


@celery_app.task(name="worker.tasks.reindex_semantic_documents")
def reindex_semantic_documents(
    project_id: int,
    article_id: int,
    entity_type: str | None = None,
) -> dict[str, object]:
    """Sync and embed semantic documents for one article scope after manual edits."""
    engine = get_engine()
    scope = SemanticReindexScope(
        project_id=int(project_id),
        article_id=int(article_id),
        entity_type=entity_type if entity_type in ("person", "location") else None,  # type: ignore[arg-type]
    )
    with Session(engine) as session:
        return run_semantic_reindex_for_scope(session, scope)


def _fail_cleanup_ai_review(engine: Any, review_id: str, message: str) -> None:
    with Session(engine) as session:
        review = session.get(StylebookCleanupAiReview, review_id)
        if review is None:
            return
        if str(review.status) == "cancelled":
            return
        review.status = "failed"
        review.error_message = message[:10000]
        review.updated_at = datetime.now(UTC)
        session.add(review)
        session.commit()


def _duplicate_cluster_ids_for_check(
    session: Session,
    *,
    check_id: str,
    stylebook_id: int,
) -> list[list[str]]:
    if check_id == "duplicate-people":
        return duplicate_person_cluster_ids(
            session,
            stylebook_id=stylebook_id,
            full_threshold=DEFAULT_FULL_SIMILARITY_THRESHOLD,
        )
    if check_id == "duplicate-organizations":
        return duplicate_organization_cluster_ids(
            session,
            stylebook_id=stylebook_id,
            full_threshold=DEFAULT_FULL_SIMILARITY_THRESHOLD,
        )
    if check_id == "duplicate-locations":
        return duplicate_location_cluster_ids(
            session,
            stylebook_id=stylebook_id,
            full_threshold=LOCATION_FULL_THRESHOLD,
            head_threshold=LOCATION_HEAD_THRESHOLD,
        )
    raise ValueError(f"Unsupported cleanup AI review check_id: {check_id}")


@celery_app.task(name="worker.tasks.execute_cleanup_ai_review")
def execute_cleanup_ai_review(review_id: str) -> None:
    """Run LLM partition proposals for all duplicate clusters in a cleanup check."""
    engine = get_engine()
    with Session(engine) as session:
        review = session.get(StylebookCleanupAiReview, review_id)
        if review is None:
            return
        if review.status != "queued":
            return
        stylebook = session.get(Stylebook, int(review.stylebook_id))
        if stylebook is None:
            _fail_cleanup_ai_review(engine, review_id, "Stylebook not found")
            return
        check_id = str(review.check_id)
        stylebook_id = int(review.stylebook_id)
        organization_id = int(stylebook.organization_id)
        model = (review.provider_model_id or "").strip() or "gpt-5-nano"
        model_config_id = review.ai_model_config_id
        try:
            cluster_id_lists = _duplicate_cluster_ids_for_check(
                session,
                check_id=check_id,
                stylebook_id=stylebook_id,
            )
        except ValueError as exc:
            _fail_cleanup_ai_review(engine, review_id, str(exc))
            return
        review.status = "running"
        review.cluster_count = len(cluster_id_lists)
        review.processed_cluster_count = 0
        review.proposal_count = 0
        review.updated_at = datetime.now(UTC)
        session.add(review)
        session.commit()

    cluster_payloads: list[list] = []
    with Session(engine) as session:
        review = session.get(StylebookCleanupAiReview, review_id)
        if review is None:
            return
        stylebook = session.get(Stylebook, int(review.stylebook_id))
        if stylebook is None:
            _fail_cleanup_ai_review(engine, review_id, "Stylebook not found")
            return
        check_id = str(review.check_id)
        stylebook_id = int(review.stylebook_id)
        organization_id = int(stylebook.organization_id)
        model = (review.provider_model_id or "").strip() or "gpt-5-nano"
        model_config_id = review.ai_model_config_id
        for member_ids in cluster_id_lists:
            members = load_cluster_members(
                session,
                check_id=check_id,
                stylebook_id=stylebook_id,
                organization_id=organization_id,
                member_ids=member_ids,
            )
            if len(members) >= 2:
                cluster_payloads.append(members)
        session.commit()

    try:
        run_cleanup_review_clusters(
            engine,
            review_id=review_id,
            check_id=check_id,
            stylebook_id=stylebook_id,
            members_by_cluster=cluster_payloads,
            model=model,
            model_config_id=model_config_id,
        )
    except Exception as exc:
        logger.exception("execute_cleanup_ai_review failed")
        _fail_cleanup_ai_review(engine, review_id, str(exc))


def _fail_cleanup_check_run(engine: Any, run_id: str, message: str) -> None:
    with Session(engine) as session:
        run = session.get(StylebookCleanupCheckRun, run_id)
        if run is None:
            return
        if str(run.status) in ("succeeded", "failed", "cancelled"):
            return
        run.status = "failed"
        run.error_message = message[:10000]
        run.completed_at = datetime.now(UTC)
        run.updated_at = datetime.now(UTC)
        session.add(run)
        session.commit()


@celery_app.task(name="worker.tasks.execute_cleanup_check_run")
def execute_cleanup_check_run(run_id: str) -> None:
    """Execute one queued cleanup check run and persist cached candidate rows."""
    engine = get_engine()
    with Session(engine) as session:
        run = session.get(StylebookCleanupCheckRun, run_id)
        if run is None:
            return
        if run.status != "queued":
            return
        stylebook = session.get(Stylebook, int(run.stylebook_id))
        if stylebook is None:
            _fail_cleanup_check_run(engine, run_id, "Stylebook not found")
            return
        scope_payload = run.scope_json if isinstance(run.scope_json, dict) else {}
        try:
            scope = CleanupRunScope(
                stylebook_id=int(run.stylebook_id),
                organization_id=int(
                    scope_payload.get("organization_id", stylebook.organization_id)
                ),
                check_id=str(run.check_id),
                full_threshold=float(
                    scope_payload.get("full_threshold", DEFAULT_FULL_SIMILARITY_THRESHOLD)
                ),
                head_threshold=float(
                    scope_payload.get("head_threshold", LOCATION_HEAD_THRESHOLD)
                ),
                project_ids=tuple(scope_payload["project_ids"])
                if isinstance(scope_payload.get("project_ids"), list)
                else None,
                project_slug=scope_payload.get("project_slug"),
            )
        except (TypeError, ValueError) as exc:
            _fail_cleanup_check_run(engine, run_id, f"Invalid run scope: {exc}")
            return
        run.status = "running"
        run.started_at = datetime.now(UTC)
        run.error_message = None
        run.updated_at = datetime.now(UTC)
        session.add(run)
        session.commit()

    try:
        with Session(engine) as session:
            run = session.get(StylebookCleanupCheckRun, run_id)
            if run is None:
                return
            scope_payload = run.scope_json if isinstance(run.scope_json, dict) else {}
            scope = CleanupRunScope(
                stylebook_id=int(run.stylebook_id),
                organization_id=int(scope_payload.get("organization_id", 0)),
                check_id=str(run.check_id),
                full_threshold=float(
                    scope_payload.get("full_threshold", DEFAULT_FULL_SIMILARITY_THRESHOLD)
                ),
                head_threshold=float(
                    scope_payload.get("head_threshold", LOCATION_HEAD_THRESHOLD)
                ),
                project_ids=tuple(scope_payload["project_ids"])
                if isinstance(scope_payload.get("project_ids"), list)
                else None,
                project_slug=scope_payload.get("project_slug"),
            )
            if scope.check_id == "questionable-organization-canonicals":
                from worker.substrate.cleanup.questionable_organizations_llm import (
                    resolve_questionable_organization_llm_context,
                )

                llm_context = resolve_questionable_organization_llm_context(
                    session,
                    scope=scope,
                )
                with _env_overlay(llm_context.api_key_overlay):
                    items = build_cleanup_check_items(
                        session,
                        scope=scope,
                        call_llm=_call_llm_with_env_api_keys,
                        questionable_org_model=llm_context.model,
                        questionable_org_model_config_id=llm_context.model_config_id,
                    )
            else:
                items = build_cleanup_check_items(session, scope=scope, call_llm=call_llm)
            session.refresh(run)
            if str(run.status) == "cancelled":
                return
            persist_cleanup_check_results(session, run=run, items=items)
            run.status = "succeeded"
            run.completed_at = datetime.now(UTC)
            run.updated_at = datetime.now(UTC)
            session.add(run)
            session.commit()
    except Exception as exc:
        logger.exception("execute_cleanup_check_run failed")
        _fail_cleanup_check_run(engine, run_id, str(exc))


def _fail_candidate_ai_review(engine: Any, review_id: str, message: str) -> None:
    with Session(engine) as session:
        review = session.get(StylebookCandidateAiReview, review_id)
        if review is None:
            return
        if str(review.status) == "cancelled":
            return
        review.status = "failed"
        review.error_message = message[:10000]
        review.updated_at = datetime.now(UTC)
        session.add(review)
        session.commit()


@celery_app.task(name="worker.tasks.execute_candidate_ai_review")
def execute_candidate_ai_review(review_id: str) -> None:
    """Run LLM recommendations for open candidate queue rows."""
    engine = get_engine()
    entity_type: str = ""
    stylebook_id = 0
    project_id = 0
    model = "gpt-5-nano"
    model_config_id: str | None = None
    candidate_ids: list[int] = []
    with Session(engine) as session:
        review = session.get(StylebookCandidateAiReview, review_id)
        if review is None:
            return
        if review.status != "queued":
            return
        stylebook = session.get(Stylebook, int(review.stylebook_id))
        if stylebook is None:
            _fail_candidate_ai_review(engine, review_id, "Stylebook not found")
            return
        entity_type = str(review.entity_type).strip()
        stylebook_id = int(review.stylebook_id)
        project_id = int(review.project_id)
        model = (review.provider_model_id or "").strip() or "gpt-5-nano"
        model_config_id = review.ai_model_config_id
        try:
            candidate_ids = list_open_candidate_ids_for_review(
                session,
                entity_type=entity_type,  # type: ignore[arg-type]
                project_id=project_id,
            )
        except ValueError as exc:
            _fail_candidate_ai_review(engine, review_id, str(exc))
            return
        review.status = "running"
        review.candidate_count = len(candidate_ids)
        review.processed_count = 0
        review.recommendation_count = 0
        review.updated_at = datetime.now(UTC)
        session.add(review)
        session.commit()

    try:
        run_candidate_ai_review(
            engine,
            review_id=review_id,
            entity_type=entity_type,  # type: ignore[arg-type]
            stylebook_id=stylebook_id,
            project_id=project_id,
            candidate_ids=candidate_ids,
            model=model,
            model_config_id=model_config_id,
        )
    except Exception as exc:
        logger.exception("execute_candidate_ai_review failed")
        _fail_candidate_ai_review(engine, review_id, str(exc))
