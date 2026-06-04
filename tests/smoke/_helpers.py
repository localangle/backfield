from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from backfield_db import (
    AgateProcessedItem,
    AgateRun,
    BackfieldAiCallRecord,
    StylebookConnection,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    StylebookLocationMeta,
    SubstrateArticle,
    SubstrateImage,
    SubstrateLocation,
    SubstrateLocationCache,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from sqlalchemy import delete
from sqlmodel import Session, select

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5433/backfield"


def load_repo_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(_REPO_ROOT / ".env", override=False)


def log(msg: str) -> None:
    print(msg, flush=True)


def http_error_detail(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        response = exc.response
        body = (response.text or "")[:4000]
        return f"{response.status_code} {response.request.method} {response.request.url!s}\n{body}"
    return str(exc)


def assert_object(response: httpx.Response, context: str) -> dict[str, Any]:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"{context} returned non-object payload: {payload!r}")
    return payload


def assert_list(response: httpx.Response, context: str) -> list[Any]:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise RuntimeError(f"{context} returned non-list payload: {payload!r}")
    return payload


def wait_for_terminal_run(
    client: httpx.Client,
    run_id: str,
    *,
    timeout_s: float,
    interval_s: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        payload = assert_object(client.get(f"/runs/{run_id}"), f"run {run_id}")
        status = str(payload.get("status") or "")
        if status in {"succeeded", "failed"}:
            return payload
        time.sleep(interval_s)
    raise RuntimeError(f"Timed out waiting for run {run_id} to finish")


def resolve_run_execution_output(
    client: httpx.Client,
    terminal_run: dict[str, Any],
    *,
    whole_run_markers: tuple[str, ...] = (
        "stylebook_output",
        "text_input",
        "geocode_agent",
    ),
) -> dict[str, Any]:
    """Return executor node outputs for a terminal run.

    Single-item runs pin ``graph_spec_json`` on ``run.result`` and store executor
    output on ``agate_processed_item.result_json``; legacy whole-graph runs embed
    output directly on ``run.result``.
    """
    run_id = str(terminal_run["id"])
    result = terminal_run.get("result")
    if isinstance(result, dict) and any(key in result for key in whole_run_markers):
        return result

    item_id: int | None = None
    processed_items = terminal_run.get("processed_items")
    if isinstance(processed_items, list) and processed_items:
        first = processed_items[0]
        if isinstance(first, dict) and isinstance(first.get("id"), int):
            item_id = int(first["id"])
    if item_id is None and isinstance(result, dict):
        result_items = result.get("items")
        if isinstance(result_items, list) and result_items:
            first = result_items[0]
            if isinstance(first, dict) and isinstance(first.get("id"), int):
                item_id = int(first["id"])
    if item_id is None:
        raise RuntimeError(
            f"Run {run_id} missing processed item id for execution output: {terminal_run!r}"
        )

    item_detail = assert_object(
        client.get(f"/runs/{run_id}/items/{item_id}"),
        f"processed item {item_id}",
    )
    output = item_detail.get("output")
    if not isinstance(output, dict):
        raise RuntimeError(f"Processed item {item_id} output must be an object: {output!r}")
    return output


def wait_for_run_status(
    client: httpx.Client,
    run_id: str,
    *,
    allowed_statuses: set[str],
    timeout_s: float,
    interval_s: float,
) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        payload = assert_object(client.get(f"/runs/{run_id}"), f"run {run_id}")
        status = str(payload.get("status") or "")
        if status in allowed_statuses:
            return payload
        time.sleep(interval_s)
    allowed = ", ".join(sorted(allowed_statuses))
    raise RuntimeError(f"Timed out waiting for run {run_id} to reach one of: {allowed}")


def ensure_health(
    *,
    agate_base: str,
    stylebook_base: str,
    core_base: str | None = None,
    agate_headers: dict[str, str] | None = None,
    stylebook_headers: dict[str, str] | None = None,
) -> None:
    if core_base:
        with httpx.Client(base_url=core_base, timeout=10.0) as core:
            payload = assert_object(core.get("/health"), "Core health")
            if payload.get("ok") is not True:
                raise RuntimeError(f"Core health failed: {payload}")

    with httpx.Client(base_url=agate_base, timeout=10.0, headers=agate_headers) as agate:
        agate_payload = assert_object(agate.get("/health"), "Agate health")
        if agate_payload.get("ok") is not True:
            raise RuntimeError(f"Agate health failed: {agate_payload}")

    with httpx.Client(
        base_url=stylebook_base,
        timeout=10.0,
        headers=stylebook_headers,
    ) as stylebook:
        stylebook_payload = assert_object(stylebook.get("/health"), "Stylebook health")
        if stylebook_payload.get("ok") is not True:
            raise RuntimeError(f"Stylebook health failed: {stylebook_payload}")


def session_cookie_headers(session_token: str) -> dict[str, str]:
    return {"Cookie": f"session={session_token}"}


@dataclass(frozen=True)
class SessionContext:
    session_token: str
    user: dict[str, Any]
    workspace: dict[str, Any]
    project: dict[str, Any]

    @property
    def organization_id(self) -> int:
        raw = self.user.get("organization_id")
        if not isinstance(raw, int):
            raise RuntimeError(f"Session user missing organization_id: {self.user!r}")
        return raw

    @property
    def project_id(self) -> int:
        raw = self.project.get("id")
        if not isinstance(raw, int):
            raise RuntimeError(f"Session project missing id: {self.project!r}")
        return raw

    @property
    def project_slug(self) -> str:
        slug = self.project.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            raise RuntimeError(f"Session project missing slug: {self.project!r}")
        return slug


@dataclass(frozen=True)
class SmokeDataSnapshot:
    article_ids: frozenset[int]
    image_ids: frozenset[int]
    location_ids: frozenset[int]
    mention_ids: frozenset[int]
    occurrence_ids: frozenset[int]
    cache_ids: frozenset[int]
    canonical_ids: frozenset[str]


def keep_smoke_data() -> bool:
    raw = os.environ.get("SMOKE_KEEP_DATA", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def login_session_context(
    *,
    core_base: str,
    email: str,
    password: str,
    workspace_slug: str,
    project_slug: str,
    bootstrap_first_user: bool = False,
) -> SessionContext:
    with httpx.Client(base_url=core_base, timeout=30.0) as core:
        core_health = assert_object(core.get("/health"), "Core health")
        if core_health.get("ok") is not True:
            raise RuntimeError(f"Core health failed: {core_health}")

        if bootstrap_first_user:
            boot = core.post(
                "/v1/bootstrap/first-user",
                json={"email": email, "password": password},
            )
            if boot.status_code not in (200, 400):
                boot.raise_for_status()

        login = core.post("/v1/auth/login", json={"email": email, "password": password})
        login.raise_for_status()
        session_token = core.cookies.get("session")
        if not session_token:
            raise RuntimeError("Login did not set session cookie")

        user = assert_object(core.get("/v1/auth/me"), "Core auth me")
        if user.get("authenticated") is not True:
            raise RuntimeError(f"Core auth me returned unauthenticated payload: {user}")

        workspaces = assert_list(core.get("/v1/me/workspaces"), "Core workspaces")
        workspace = next(
            (
                row
                for row in workspaces
                if isinstance(row, dict) and row.get("slug") == workspace_slug
            ),
            None,
        )
        if workspace is None:
            raise RuntimeError(
                f"Workspace slug {workspace_slug!r} not found in /v1/me/workspaces"
            )

        projects = workspace.get("projects")
        if not isinstance(projects, list):
            raise RuntimeError(f"workspace.projects must be a list: {workspace!r}")
        project = next(
            (
                row
                for row in projects
                if isinstance(row, dict) and row.get("slug") == project_slug
            ),
            None,
        )
        if project is None:
            raise RuntimeError(
                f"Project slug {project_slug!r} not found in workspace {workspace_slug!r}"
            )

        return SessionContext(
            session_token=session_token,
            user=user,
            workspace=workspace,
            project=project,
        )


def default_stylebook_for_org(
    *,
    stylebook_base: str,
    session_token: str,
    organization_id: int,
) -> dict[str, Any]:
    headers = session_cookie_headers(session_token)
    with httpx.Client(base_url=stylebook_base, timeout=10.0, headers=headers) as stylebook:
        rows = assert_list(
            stylebook.get(f"/v1/organizations/{organization_id}/stylebooks"),
            "Stylebook list",
        )
    stylebook_row = next(
        (row for row in rows if isinstance(row, dict) and row.get("is_default") is True),
        None,
    )
    if stylebook_row is None:
        stylebook_row = next((row for row in rows if isinstance(row, dict)), None)
    if stylebook_row is None:
        raise RuntimeError(f"No stylebooks found for organization {organization_id}")
    return stylebook_row


def capture_smoke_snapshot(
    session: Session,
    *,
    project_id: int,
    stylebook_id: int | None = None,
) -> SmokeDataSnapshot:
    article_ids = frozenset(
        int(row)
        for row in session.exec(
            select(SubstrateArticle.id).where(SubstrateArticle.project_id == project_id)
        ).all()
        if row is not None
    )
    image_ids = frozenset(
        int(row)
        for row in session.exec(
            select(SubstrateImage.id)
            .join(SubstrateArticle, SubstrateArticle.id == SubstrateImage.article_id)
            .where(SubstrateArticle.project_id == project_id)
        ).all()
        if row is not None
    )
    location_ids = frozenset(
        int(row)
        for row in session.exec(
            select(SubstrateLocation.id).where(SubstrateLocation.project_id == project_id)
        ).all()
        if row is not None
    )
    mention_ids = frozenset(
        int(row)
        for row in session.exec(
            select(SubstrateLocationMention.id)
            .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
            .where(SubstrateArticle.project_id == project_id)
        ).all()
        if row is not None
    )
    occurrence_ids = frozenset(
        int(row)
        for row in session.exec(
            select(SubstrateLocationMentionOccurrence.id)
            .join(
                SubstrateLocationMention,
                SubstrateLocationMention.id
                == SubstrateLocationMentionOccurrence.location_mention_id,
            )
            .join(SubstrateArticle, SubstrateArticle.id == SubstrateLocationMention.article_id)
            .where(SubstrateArticle.project_id == project_id)
        ).all()
        if row is not None
    )
    cache_ids = frozenset(
        int(row)
        for row in session.exec(
            select(SubstrateLocationCache.id).where(SubstrateLocationCache.project_id == project_id)
        ).all()
        if row is not None
    )
    canonical_ids = frozenset(
        str(row)
        for row in (
            session.exec(
                select(StylebookLocationCanonical.id).where(
                    StylebookLocationCanonical.stylebook_id == stylebook_id
                )
            ).all()
            if stylebook_id is not None
            else []
        )
        if row is not None
    )
    return SmokeDataSnapshot(
        article_ids=article_ids,
        image_ids=image_ids,
        location_ids=location_ids,
        mention_ids=mention_ids,
        occurrence_ids=occurrence_ids,
        cache_ids=cache_ids,
        canonical_ids=canonical_ids,
    )


def delete_smoke_run(session: Session, *, run_id: str) -> None:
    session.exec(delete(BackfieldAiCallRecord).where(BackfieldAiCallRecord.run_id == run_id))
    session.exec(delete(AgateProcessedItem).where(AgateProcessedItem.run_id == run_id))
    session.exec(delete(AgateRun).where(AgateRun.id == run_id))


def delete_smoke_substrate_rows(
    session: Session,
    *,
    article_ids: set[int] | frozenset[int] = frozenset(),
    location_ids: set[int] | frozenset[int] = frozenset(),
) -> None:
    if article_ids:
        article_id_list = sorted(article_ids)
        mention_rows = list(
            session.exec(
                select(SubstrateLocationMention).where(
                    SubstrateLocationMention.article_id.in_(article_id_list)
                )
            ).all()
        )
        mention_ids = [int(row.id) for row in mention_rows if row.id is not None]
        if mention_ids:
            session.exec(
                delete(SubstrateLocationMentionOccurrence).where(
                    SubstrateLocationMentionOccurrence.location_mention_id.in_(mention_ids)
                )
            )
        session.exec(delete(SubstrateLocationMention).where(SubstrateLocationMention.article_id.in_(article_id_list)))
        session.exec(delete(SubstrateImage).where(SubstrateImage.article_id.in_(article_id_list)))
        session.exec(delete(SubstrateArticle).where(SubstrateArticle.id.in_(article_id_list)))

    if location_ids:
        session.exec(delete(SubstrateLocation).where(SubstrateLocation.id.in_(sorted(location_ids))))


def delete_smoke_canonical(
    session: Session,
    *,
    canonical_id: str,
    allowed_linked_location_ids: set[int] | frozenset[int] = frozenset(),
) -> bool:
    linked_ids = {
        int(row)
        for row in session.exec(
            select(SubstrateLocation.id).where(
                SubstrateLocation.stylebook_location_canonical_id == canonical_id
            )
        ).all()
        if row is not None
    }
    if linked_ids - set(allowed_linked_location_ids):
        return False

    session.exec(
        delete(StylebookLocationAlias).where(
            StylebookLocationAlias.location_canonical_id == canonical_id
        )
    )
    session.exec(
        delete(StylebookLocationMeta).where(
            StylebookLocationMeta.stylebook_location_canonical_id == canonical_id
        )
    )
    session.exec(
        delete(StylebookConnection).where(
            StylebookConnection.from_entity_type == "location",
            StylebookConnection.from_entity_id == canonical_id,
        )
    )
    session.exec(
        delete(StylebookConnection).where(
            StylebookConnection.to_entity_type == "location",
            StylebookConnection.to_entity_id == canonical_id,
        )
    )
    session.exec(
        delete(StylebookLocationCanonical).where(StylebookLocationCanonical.id == canonical_id)
    )
    return True


def cleanup_snapshot_delta(
    session: Session,
    *,
    before: SmokeDataSnapshot,
    after: SmokeDataSnapshot,
) -> None:
    new_article_ids = set(after.article_ids - before.article_ids)
    new_location_ids = set(after.location_ids - before.location_ids)

    delete_smoke_substrate_rows(
        session,
        article_ids=new_article_ids,
        location_ids=new_location_ids,
    )

    for cache_id in sorted(after.cache_ids - before.cache_ids):
        session.exec(delete(SubstrateLocationCache).where(SubstrateLocationCache.id == cache_id))

    for canonical_id in sorted(after.canonical_ids - before.canonical_ids):
        delete_smoke_canonical(
            session,
            canonical_id=canonical_id,
            allowed_linked_location_ids=new_location_ids,
        )


def get_database_url() -> str:
    return os.environ.get(
        "BACKFIELD_DATABASE_URL",
        os.environ.get("DATABASE_URL", _DEFAULT_DATABASE_URL),
    )


@contextmanager
def smoke_db_session():
    os.environ.setdefault("BACKFIELD_DATABASE_URL", get_database_url())
    from backfield_db.session import get_engine

    with Session(get_engine()) as session:
        yield session


load_repo_dotenv()
