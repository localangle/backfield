"""Production worker Dockerfile contract tests."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_WORKER_DOCKERFILE = _REPO_ROOT / "apps" / "worker" / "Dockerfile"


def _read_dockerfile() -> str:
    return _WORKER_DOCKERFILE.read_text(encoding="utf-8")


def _prod_stage(dockerfile_text: str) -> str:
    match = re.search(r"FROM .* AS prod\b", dockerfile_text)
    if match is None:
        return ""
    remainder = dockerfile_text[match.start() :]
    next_from = re.search(r"\nFROM ", remainder)
    if next_from is None:
        return remainder
    return remainder[: next_from.start()]


def test_worker_dockerfile_declares_prod_target_with_build_metadata() -> None:
    text = _read_dockerfile()
    assert "AS prod" in text
    assert "ARG APP_VERSION" in text
    assert "ARG GIT_SHA" in text
    assert "ARG BUILD_TIME" in text
    assert "ENV APP_VERSION" in text
    assert "CELERY_WORKER_CONCURRENCY=16" in _prod_stage(text)
    assert "--concurrency=16" not in text
    assert "--reload" not in _prod_stage(text)


def test_worker_entrypoint_uses_celery_worker_concurrency_env() -> None:
    entrypoint = (
        _REPO_ROOT / "apps" / "worker" / "scripts" / "entrypoint.sh"
    ).read_text(encoding="utf-8")
    assert 'CONCURRENCY="${CELERY_WORKER_CONCURRENCY:-16}"' in entrypoint
    assert '--concurrency "${CONCURRENCY}"' in entrypoint
    assert "log_worker_startup" in entrypoint


def test_compose_worker_uses_dev_target_and_entrypoint() -> None:
    compose = (_REPO_ROOT / "infra" / "docker-compose.yml").read_text(encoding="utf-8")
    worker_block = compose.split("  worker:", 1)[1].split("\n\n", 1)[0]
    assert "target: dev" in worker_block
    assert "command:" not in worker_block


def test_prod_worker_image_logs_version_and_respects_concurrency() -> None:
    if os.environ.get("BACKFIELD_DOCKER_PROD_TESTS") != "1":
        pytest.skip(
            "set BACKFIELD_DOCKER_PROD_TESTS=1 to build and run the production worker image"
        )

    version = "v9.8.7"
    git_sha = "deadbeef"
    build_time = "2026-06-26T12:00:00Z"
    concurrency = "7"
    tag = "backfield-worker:prod-test"

    build = subprocess.run(
        [
            "docker",
            "build",
            "-f",
            str(_WORKER_DOCKERFILE),
            "--target",
            "prod",
            "--build-arg",
            f"APP_VERSION={version}",
            "--build-arg",
            f"GIT_SHA={git_sha}",
            "--build-arg",
            f"BUILD_TIME={build_time}",
            "-t",
            tag,
            str(_REPO_ROOT),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert build.returncode == 0, build.stderr

    redis_name = "backfield-prod-test-worker-redis"
    worker_name = "backfield-prod-test-worker"
    network_name = "backfield-prod-test-worker-net"
    subprocess.run(
        ["docker", "rm", "-f", redis_name, worker_name],
        capture_output=True,
        check=False,
    )
    subprocess.run(["docker", "network", "rm", network_name], capture_output=True, check=False)
    subprocess.run(["docker", "network", "create", network_name], capture_output=True, check=True)
    redis_run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            redis_name,
            "--network",
            network_name,
            "redis:7",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert redis_run.returncode == 0, redis_run.stderr

    worker_run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            worker_name,
            "--network",
            network_name,
            "-e",
            f"REDIS_URL=redis://{redis_name}:6379/0",
            "-e",
            f"CELERY_WORKER_CONCURRENCY={concurrency}",
            tag,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert worker_run.returncode == 0, worker_run.stderr

    try:
        deadline = time.time() + 45
        last_logs = ""
        while time.time() < deadline:
            logs = subprocess.run(
                ["docker", "logs", worker_name],
                capture_output=True,
                text=True,
                check=True,
            )
            last_logs = logs.stdout + logs.stderr
            has_startup = '"event": "worker_startup"' in last_logs
            has_concurrency = f'"concurrency": "{concurrency}"' in last_logs
            has_celery_pool = f"concurrency: {concurrency}" in last_logs
            if has_startup and has_concurrency and has_celery_pool:
                startup_lines = [
                    line
                    for line in last_logs.splitlines()
                    if '"event": "worker_startup"' in line
                ]
                assert startup_lines, last_logs
                startup_line = startup_lines[-1]
                payload = json.loads(startup_line[startup_line.index("{") :])
                assert payload == {
                    "event": "worker_startup",
                    "service": "worker",
                    "version": version,
                    "git_sha": git_sha,
                    "build_time": build_time,
                    "concurrency": concurrency,
                }
                inspect = subprocess.run(
                    [
                        "docker",
                        "inspect",
                        "-f",
                        "{{.Config.Entrypoint}} {{.Config.Cmd}}",
                        worker_name,
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                assert "--reload" not in inspect.stdout
                return
            time.sleep(1)
        raise AssertionError(f"Timed out waiting for worker startup logs: {last_logs}")
    finally:
        subprocess.run(
            ["docker", "rm", "-f", worker_name, redis_name],
            capture_output=True,
            check=False,
        )
        subprocess.run(["docker", "network", "rm", network_name], capture_output=True, check=False)
