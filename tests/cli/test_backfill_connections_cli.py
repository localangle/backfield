"""Tests for the connection backfill command contract."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from backfield_cli.main import main


def test_backfill_requires_explicit_scope() -> None:
    with pytest.raises(SystemExit):
        main(["backfill-connections"])


def test_backfill_defaults_to_dry_run() -> None:
    with patch(
        "backfield_cli.main.backfill_connections_cmd.run",
        return_value=0,
    ) as run:
        assert main(["backfill-connections", "--project-id", "7"]) == 0

    args = run.call_args.args[0]
    assert args.project_id == 7
    assert args.stylebook_id is None
    assert args.apply is False
    assert args.max_requests_per_article == 4


def test_backfill_rejects_request_budget_above_total_cap() -> None:
    assert (
        main(
            [
                "backfill-connections",
                "--project-id",
                "7",
                "--max-requests-per-article",
                "9",
            ]
        )
        == 2
    )
