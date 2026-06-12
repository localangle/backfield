"""Article Metadata runner for the Backfield executor."""

from __future__ import annotations

from typing import Any

from agate_runtime.runners import default_context, run_article_metadata_runtime


def run_article_metadata(params: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    return run_article_metadata_runtime(params, inputs, default_context())
