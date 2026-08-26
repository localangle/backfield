"""Dry-run-first historical automatic-connection backfill."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from backfield_ai.agate_llm_bridge import call_llm_tracked_sync
from backfield_ai.credentials import merge_project_and_org_llm_api_keys
from backfield_ai.tracking_context import (
    LlmAttemptTrackingContext,
    attach_llm_tracking_context,
    reset_llm_tracking_context,
)
from backfield_db import BackfieldProject, SubstrateArticle
from backfield_db.session import get_engine
from backfield_entities.connections.caps import MAX_TOTAL_CONNECTION_REQUESTS
from backfield_entities.connections.db_output import run_auto_connections_for_db_output
from backfield_entities.ingest.db_output_settings import DbOutputCanonicalSettings
from sqlmodel import Session, col, select


def register_subcommand(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "backfill-connections",
        help="Infer historical article connections (dry-run by default)",
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--project-id", type=int)
    scope.add_argument("--stylebook-id", type=int)
    parser.add_argument("--start-article-id", type=int)
    parser.add_argument("--end-article-id", type=int)
    parser.add_argument("--after-article-id", type=int, default=0)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--max-requests-per-article", type=int, default=16)
    parser.add_argument("--model", default="gpt-5-nano")
    parser.add_argument("--model-config-id")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.set_defaults(handler=run)


@contextmanager
def _environment_overlay(updates: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in updates}
    try:
        os.environ.update(updates)
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _call_llm(prompt: str, **kwargs: Any) -> str:
    return call_llm_tracked_sync(
        prompt=prompt,
        model=kwargs.get("model"),
        system_message=None,
        force_json=bool(kwargs.get("force_json", True)),
        max_retries=1,
        temperature=float(kwargs.get("temperature", 0.0)),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        gemini_api_key=os.getenv("GEMINI_API_KEY"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY"),
        azure_api_key=os.getenv("AZURE_API_KEY"),
        azure_api_base=os.getenv("AZURE_API_BASE"),
        project_system_prompt=None,
        timeout=300.0,
        model_config_id=kwargs.get("model_config_id"),
        allow_max_tokens_bump=False,
    )


def _project_ids_for_scope(session: Session, args: argparse.Namespace) -> list[int]:
    if args.project_id is not None:
        project = session.get(BackfieldProject, int(args.project_id))
        if project is None:
            raise ValueError(f"project {args.project_id} not found")
        return [int(args.project_id)]
    rows = session.exec(
        select(BackfieldProject.id).where(
            col(BackfieldProject.stylebook_id) == int(args.stylebook_id)
        )
    ).all()
    project_ids = [int(row) for row in rows if row is not None]
    if not project_ids:
        raise ValueError(f"no projects found for Stylebook {args.stylebook_id}")
    return project_ids


def _articles(
    session: Session,
    *,
    project_ids: list[int],
    args: argparse.Namespace,
) -> list[SubstrateArticle]:
    query = select(SubstrateArticle).where(
        col(SubstrateArticle.project_id).in_(project_ids),
        col(SubstrateArticle.id) > int(args.after_article_id),
    )
    if args.start_article_id is not None:
        query = query.where(col(SubstrateArticle.id) >= int(args.start_article_id))
    if args.end_article_id is not None:
        query = query.where(col(SubstrateArticle.id) <= int(args.end_article_id))
    return list(
        session.exec(
            query.order_by(col(SubstrateArticle.id)).limit(int(args.limit))
        ).all()
    )


def _validate_args(args: argparse.Namespace) -> None:
    if args.limit <= 0:
        raise ValueError("--limit must be positive")
    if not 1 <= args.max_requests_per_article <= MAX_TOTAL_CONNECTION_REQUESTS:
        raise ValueError(
            "--max-requests-per-article must be between 1 and "
            f"{MAX_TOTAL_CONNECTION_REQUESTS}"
        )
    if (
        args.start_article_id is not None
        and args.end_article_id is not None
        and args.start_article_id > args.end_article_id
    ):
        raise ValueError("--start-article-id cannot exceed --end-article-id")


def run(args: argparse.Namespace) -> int:
    """Run a resumable scope-bounded connection inference backfill."""
    try:
        _validate_args(args)
        with Session(get_engine()) as session:
            project_ids = _project_ids_for_scope(session, args)
            articles = _articles(session, project_ids=project_ids, args=args)

        report: dict[str, Any] = {
            "mode": "apply" if args.apply else "dry_run",
            "scope": (
                {"project_id": args.project_id}
                if args.project_id is not None
                else {"stylebook_id": args.stylebook_id}
            ),
            "processed": 0,
            "failed": 0,
            "created": 0,
            "reinforced": 0,
            "deferred": 0,
            "unprocessed": 0,
            "requests": 0,
            "articles": [],
            "resume_cursor": args.after_article_id,
        }
        settings = DbOutputCanonicalSettings(
            adjudication_model=str(args.model),
            adjudication_ai_model_config_id=args.model_config_id,
        )
        for article in articles:
            article_id = int(article.id)  # type: ignore[arg-type]
            project_id = int(article.project_id)
            with Session(get_engine()) as session:
                overlay = merge_project_and_org_llm_api_keys(session, project_id)
                tracking_token = attach_llm_tracking_context(
                    LlmAttemptTrackingContext(project_id=project_id, run_id=None)
                )
                try:
                    with _environment_overlay(overlay):
                        summary = run_auto_connections_for_db_output(
                            session,
                            project_id=project_id,
                            article_id=article_id,
                            article_text=str(article.text or ""),
                            settings=settings,
                            call_llm=_call_llm,
                            max_requests=int(args.max_requests_per_article),
                            defer_overflow=False,
                            dry_run=not bool(args.apply),
                        )
                    if args.apply and summary.get("status") != "failed":
                        session.commit()
                    else:
                        session.rollback()
                finally:
                    reset_llm_tracking_context(tracking_token)

            diagnostics = summary.get("diagnostics", {})
            report["processed"] += 1
            report["failed"] += int(summary.get("status") == "failed")
            report["created"] += int(summary.get("created", 0))
            report["reinforced"] += int(summary.get("reinforced", 0))
            report["deferred"] += int(summary.get("deferred", 0))
            report["unprocessed"] += int(summary.get("unprocessed", 0))
            report["requests"] += int(diagnostics.get("requests", 0))
            report["resume_cursor"] = article_id
            report["articles"].append(
                {
                    "article_id": article_id,
                    "project_id": project_id,
                    "status": summary.get("status"),
                    "created": summary.get("created", 0),
                    "reinforced": summary.get("reinforced", 0),
                    "diagnostics": diagnostics,
                }
            )

        rendered = json.dumps(report, indent=2, sort_keys=True)
        if args.report is not None:
            args.report.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
        return 0 if report["failed"] == 0 else 1
    except ValueError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 2
