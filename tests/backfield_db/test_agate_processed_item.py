"""Contract checks for Agate batch item table."""

from __future__ import annotations

from backfield_db import AgateProcessedItem


def test_agate_processed_item_table_name() -> None:
    assert AgateProcessedItem.__tablename__ == "agate_processed_item"
