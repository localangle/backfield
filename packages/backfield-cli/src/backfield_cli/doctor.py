"""Diagnostic checks for the local Backfield development environment."""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path

from backfield_cli.console import CONSOLE
from backfield_cli.env_file import find_repo_root
from backfield_cli.host_tooling import (
    cli_entrypoint_works,
    cli_runtime_works,
    cli_shim_source,
    cli_shim_target,
    venv_python,
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def run_checks(start: Path | None = None) -> tuple[Path | None, list[CheckResult]]:
    results: list[CheckResult] = []
    try:
        repo_root = find_repo_root(start)
    except FileNotFoundError as exc:
        results.append(CheckResult("repo root", False, str(exc)))
        return None, results

    results.append(CheckResult("repo root", True, str(repo_root)))

    uv_path = shutil.which("uv")
    results.append(
        CheckResult("uv", uv_path is not None, uv_path or "not on PATH"),
    )

    docker_path = shutil.which("docker")
    results.append(
        CheckResult("docker", docker_path is not None, docker_path or "not on PATH"),
    )

    venv_dir = repo_root / ".venv"
    python = venv_python(repo_root)
    results.append(
        CheckResult(
            ".venv",
            python.is_file(),
            str(venv_dir) if venv_dir.is_dir() else f"missing ({venv_dir})",
        ),
    )

    if python.is_file():
        entrypoint_ok = cli_entrypoint_works(repo_root)
        results.append(
            CheckResult(
                "CLI entrypoint",
                entrypoint_ok,
                "backfield_cli.main importable"
                if entrypoint_ok
                else "backfield_cli.main not importable from .venv",
            ),
        )
        runtime_ok = cli_runtime_works(repo_root)
        results.append(
            CheckResult(
                "CLI runtime imports",
                runtime_ok,
                "backfield_cli and backfield_db importable"
                if runtime_ok
                else "backfield_db not importable (run make bootstrap)",
            ),
        )
    else:
        results.append(
            CheckResult("CLI entrypoint", False, ".venv python missing"),
        )
        results.append(
            CheckResult("CLI runtime imports", False, ".venv python missing"),
        )

    env_path = repo_root / ".env"
    if env_path.is_file():
        results.append(CheckResult(".env", True, str(env_path)))
    else:
        example = repo_root / ".env.example"
        hint = f"missing; copy from {example.name}" if example.is_file() else "missing"
        results.append(CheckResult(".env", False, hint))

    compose = repo_root / "infra" / "docker-compose.yml"
    results.append(
        CheckResult("compose file", compose.is_file(), str(compose)),
    )

    launcher = cli_shim_source(repo_root)
    results.append(
        CheckResult(
            "project launcher",
            launcher.is_file(),
            str(launcher),
        ),
    )

    shim = cli_shim_target(repo_root)
    if shim.is_file():
        results.append(CheckResult("venv launcher", True, str(shim)))
    else:
        results.append(
            CheckResult(
                "venv launcher",
                False,
                f"missing; run make bootstrap ({shim})",
            ),
        )

    return repo_root, results


def register_subcommand(subparsers) -> None:
    parser = subparsers.add_parser(
        "doctor",
        help="Check local development environment (repo, uv, docker, .venv, .env)",
    )
    parser.set_defaults(handler=_run)


def _run(_args: argparse.Namespace) -> int:
    _repo_root, results = run_checks()
    failed = 0
    for result in results:
        if result.ok:
            CONSOLE.print(f"[green]ok[/green]  {result.name}: {result.detail}")
        else:
            CONSOLE.print(f"[red]fail[/red] {result.name}: {result.detail}")
            failed += 1

    if failed:
        CONSOLE.print(
            f"\n[red]{failed} check(s) failed.[/red] "
            "Run `make bootstrap` from the repo root, then `backfield doctor` again."
        )
        return 1

    CONSOLE.print("\n[green]All checks passed.[/green]")
    return 0
