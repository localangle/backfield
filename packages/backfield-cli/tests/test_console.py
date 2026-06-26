"""Tests for CLI console presentation helpers."""

from __future__ import annotations

from backfield_cli.console import BANNER, print_banner


def test_banner_preserves_block_logo() -> None:
    lines = BANNER.splitlines()
    assert len(lines) == 7
    assert lines[0].startswith("░████████")
    assert lines[-1].startswith("░█████████")


def test_print_banner_renders_without_error(monkeypatch) -> None:
    printed: list[object] = []
    monkeypatch.setattr("backfield_cli.console.CONSOLE.print", lambda value, **_: printed.append(value))
    print_banner()
    assert len(printed) == 1
