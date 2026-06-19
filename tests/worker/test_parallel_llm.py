"""Tests for session-free LLM batch helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from worker.substrate.canonical.parallel_llm import commit_session_before_session_free_llm


def test_commit_session_before_session_free_llm_commits() -> None:
    session = MagicMock()
    commit_session_before_session_free_llm(session)
    session.commit.assert_called_once()
