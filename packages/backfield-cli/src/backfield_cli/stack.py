"""Docker Compose stack helpers for local init and operator commands."""

from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from backfield_cli.env_file import find_repo_root

logger = logging.getLogger(__name__)

READINESS_TIMEOUT_SECONDS = 180
READINESS_POLL_INTERVAL_SECONDS = 2

API_READINESS: tuple[tuple[str, int], ...] = (
    ("agate-api", 8000),
    ("stylebook-api", 8003),
    ("core-api", 8004),
)

HOST_DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5433/backfield"

COMPOSE_FILE_ENV = "BACKFIELD_COMPOSE_FILE"


@dataclass(frozen=True)
class ComposeContext:
    """Resolved location of the compose file, its env file, and the repo root."""

    compose_file: Path
    env_file: Path
    repo_root: Path


def resolve_compose_context(compose_file: str | None = None) -> ComposeContext:
    """Resolve the compose file to operate on.

    Precedence: explicit ``--compose-file`` argument, then ``BACKFIELD_COMPOSE_FILE``
    env var, then repo-root discovery (``find_repo_root() / infra/docker-compose.yml``).
    """
    override = compose_file or os.environ.get(COMPOSE_FILE_ENV)
    if override:
        resolved = Path(override).expanduser().resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Compose file not found: {resolved}")
        repo_root = resolved.parent.parent
        return ComposeContext(
            compose_file=resolved,
            env_file=repo_root / ".env",
            repo_root=repo_root,
        )
    repo_root = find_repo_root()
    return ComposeContext(
        compose_file=repo_root / "infra" / "docker-compose.yml",
        env_file=repo_root / ".env",
        repo_root=repo_root,
    )

_READINESS_CHECK = """
import json
import sys
import urllib.error
import urllib.request

try:
    with urllib.request.urlopen({url!r}, timeout=3) as response:
        payload = json.loads(response.read().decode())
except urllib.error.URLError as exc:
    print(exc, file=sys.stderr)
    sys.exit(1)

if payload.get("ok") is True:
    sys.exit(0)
print("unexpected readyz payload:", payload, file=sys.stderr)
sys.exit(1)
"""


def compose_command(repo_root: Path, *args: str) -> list[str]:
    context = ComposeContext(
        compose_file=repo_root / "infra" / "docker-compose.yml",
        env_file=repo_root / ".env",
        repo_root=repo_root,
    )
    return compose_command_for_context(context, *args)


def compose_command_for_context(context: ComposeContext, *args: str) -> list[str]:
    return [
        "docker",
        "compose",
        "-f",
        str(context.compose_file),
        "--env-file",
        str(context.env_file),
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


def _check_service_readiness(repo_root: Path, service: str, port: int) -> bool:
    url = f"http://127.0.0.1:{port}/readyz"
    result = subprocess.run(
        compose_command(
            repo_root,
            "exec",
            "-T",
            service,
            "python",
            "-c",
            _READINESS_CHECK.format(url=url),
        ),
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def wait_for_api_readiness(
    repo_root: Path,
    *,
    timeout_seconds: float = READINESS_TIMEOUT_SECONDS,
    poll_interval_seconds: float = READINESS_POLL_INTERVAL_SECONDS,
) -> None:
    """Wait until each API's /readyz returns ok:true inside its container."""
    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None

    while time.monotonic() < deadline:
        all_ready = True
        for service, port in API_READINESS:
            if _check_service_readiness(repo_root, service, port):
                continue
            all_ready = False
            last_error = f"{service}: not ready"
            break

        if all_ready:
            logger.info("All API readiness checks passed")
            return

        time.sleep(poll_interval_seconds)

    hint = (
        " Check `docker compose -f infra/docker-compose.yml ps` and service logs "
        "(for example `docker compose -f infra/docker-compose.yml logs agate-api`)."
    )
    raise TimeoutError(f"Timed out waiting for API readiness ({last_error}).{hint}")
