from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from sqlmodel import Session

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
