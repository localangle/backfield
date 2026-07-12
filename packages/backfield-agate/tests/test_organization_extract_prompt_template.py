"""Tests for OrganizationExtract prompt resolution."""

from __future__ import annotations

from agate_nodes.organization_extract.prompt_template import (
    resolve_organization_extract_prompt,
)


def test_resolve_organization_extract_prompt_prefers_bundled_when_snapshot_matches() -> None:
    bundled = 'Extract organizations.\n\nReturn {{ "organizations": [] }}.\n\n{text}'
    custom = 'Extract organizations.\n\nReturn { "organizations": [] }.\n\n{text}'
    assert resolve_organization_extract_prompt(bundled=bundled, custom=custom) == bundled


def test_resolve_organization_extract_prompt_keeps_real_custom_prompt() -> None:
    bundled = "Extract organizations from {text}"
    custom = "Only extract government agencies from {text}"
    assert resolve_organization_extract_prompt(bundled=bundled, custom=custom) == custom


def test_resolve_organization_extract_prompt_uses_bundled_when_custom_empty() -> None:
    bundled = "Extract organizations from {text}"
    assert resolve_organization_extract_prompt(bundled=bundled, custom="") == bundled
