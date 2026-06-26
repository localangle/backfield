"""Docker Compose stack helpers for local init."""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

API_READINESS: tuple[tuple[str, str, int], ...] = (
    ("agate-api", "http://127.0.0.1:8000/readyz", 8000),
    ("stylebook-api", "http://127.0.0.1:8003/readyz", 8003),
    ("core-api", "http://127.0.0.1:8004/readyz", 8004),
)

HOST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5433/backfield"


def compose_command(repo_root: Path, *args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(repo_root / "infra" / "docker-compose.yml"),
        "--env-file",
        str(repo_root / ".env"),
        *args,
    ]


def bring_up_stack(repo_root: Path) -> None:
    logger.info("Starting Backfield stack (docker compose up -d --build)...")
    subprocess.run(
        compose_command(repo_root, "up", "-d", "--build"),
        check=True,
    )


def run_compose_migrate(repo_root: Path) -> None:
    logger.info("Running database migrations...")
    subprocess.run(
        compose_command(repo_root, "run", "--rm", "migrate"),
        check=True,
    )


def configure_host_database_env() -> None:
    import os

    os.environ.setdefault("BACKFIELD_DATABASE_URL_DIRECT", HOST_DATABASE_URL)
    os.environ.setdefault("BACKFIELD_DATABASE_URL", HOST_DATABASE_URL)
    os.environ.setdefault("DATABASE_URL", HOST_DATABASE_URL)


def wait_for_api_readiness(
    *,
    timeout_s: float = 180.0,
    poll_interval_s: float = 2.0,
) -> None:
    deadline = time.time() + timeout_s
    last_errors: dict[str, str] = {}
    while time.time() < deadline:
        all_ready = True
        for service_name, url, _port in API_READINESS:
            try:
                response = httpx.get(url, timeout=3.0)
                if response.status_code == 200:
                    payload = response.json()
                    if payload.get("ok") is True:
                        continue
                    last_errors[service_name] = f"readyz not ok: {payload!r}"
                else:
                    last_errors[service_name] = f"HTTP {response.status_code}"
            except httpx.HTTPError as exc:
                last_errors[service_name] = str(exc)
            all_ready = False
        if all_ready:
            logger.info("All API readiness checks passed")
            return
        time.sleep(poll_interval_s)
    details = ", ".join(f"{name}: {err}" for name, err in sorted(last_errors.items()))
    raise TimeoutError(f"Timed out waiting for API readiness ({details})")
