"""Production API Dockerfile contract tests."""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_API_DOCKERFILES: tuple[tuple[str, str, int, str], ...] = (
    ("apps/agate-api/Dockerfile", "agate-api", 8000, "agate-api"),
    ("apps/core-api/Dockerfile", "core-api", 8004, "core-api"),
    ("apps/stylebook-api/Dockerfile", "stylebook-api", 8003, "stylebook-api"),
)


def _read_dockerfile(relative_path: str) -> str:
    return (_REPO_ROOT / relative_path).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("dockerfile", "service_name"),
    [(path, service) for path, service, _, _ in _API_DOCKERFILES],
)
def test_api_dockerfile_declares_prod_target_with_build_metadata(
    dockerfile: str,
    service_name: str,
) -> None:
    text = _read_dockerfile(dockerfile)
    assert "AS prod" in text
    assert "ARG APP_VERSION" in text
    assert "ARG GIT_SHA" in text
    assert "ARG BUILD_TIME" in text
    assert "ENV APP_VERSION" in text
    assert "--reload" not in _prod_stage(text)


def _prod_stage(dockerfile_text: str) -> str:
    match = re.search(r"FROM .* AS prod\b", dockerfile_text)
    if match is None:
        return ""
    remainder = dockerfile_text[match.start() :]
    next_from = re.search(r"\nFROM ", remainder)
    if next_from is None:
        return remainder
    return remainder[: next_from.start()]


def _curl_version_from_container(container_name: str, port: int) -> dict[str, str]:
    result = subprocess.run(
        [
            "docker",
            "exec",
            container_name,
            "python",
            "-c",
            (
                "import json, urllib.request; "
                f"print(urllib.request.urlopen('http://127.0.0.1:{port}/version').read().decode())"
            ),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    ("dockerfile", "service_name", "port", "image_tag"),
    _API_DOCKERFILES,
)
def test_prod_api_image_reports_baked_version_metadata(
    dockerfile: str,
    service_name: str,
    port: int,
    image_tag: str,
) -> None:
    if os.environ.get("BACKFIELD_DOCKER_PROD_TESTS") != "1":
        pytest.skip("set BACKFIELD_DOCKER_PROD_TESTS=1 to build and run production API images")

    version = "v9.8.7"
    git_sha = "deadbeef"
    build_time = "2026-06-26T12:00:00Z"
    tag = f"backfield-{image_tag}:prod-test"

    build = subprocess.run(
        [
            "docker",
            "build",
            "-f",
            str(_REPO_ROOT / dockerfile),
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

    container_name = f"backfield-prod-test-{image_tag.replace('/', '-')}"
    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, check=False)
    run = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            container_name,
            tag,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr

    try:
        deadline = time.time() + 30
        last_error: Exception | None = None
        while time.time() < deadline:
            try:
                payload = _curl_version_from_container(container_name, port)
                assert payload == {
                    "service": service_name,
                    "version": version,
                    "git_sha": git_sha,
                    "build_time": build_time,
                }
                ps = subprocess.run(
                    ["docker", "inspect", "-f", "{{.Config.Cmd}}", container_name],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                assert "--reload" not in ps.stdout
                return
            except (subprocess.CalledProcessError, json.JSONDecodeError, AssertionError) as exc:
                last_error = exc
            time.sleep(1)
        raise AssertionError(f"Timed out waiting for /version on {service_name}: {last_error}")
    finally:
        subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, check=False)
