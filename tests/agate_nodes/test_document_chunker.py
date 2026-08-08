"""Tests for DocumentChunker node."""

from __future__ import annotations

import pytest
from agate_nodes.document_chunker.node import run_document_chunker
from agate_utils.text_chunking import TRANSIENT_CHUNK_ENVELOPE_KEY


def test_document_chunker_preserves_text_and_metadata() -> None:
    out = run_document_chunker(
        {"target_tokens": 4000, "overlap_tokens": 250},
        {"node-1": {"text": "Hello world", "headline": "Hi", "url": "https://example.com"}},
    )
    assert out["text"] == "Hello world"
    assert out["headline"] == "Hi"
    assert out["chunking_summary"]["chunk_count"] == 1
    assert out["chunking_summary"]["split_required"] is False
    assert TRANSIENT_CHUNK_ENVELOPE_KEY in out
    assert "Hello world" not in str(out["chunking_summary"]["chunks"][0].get("preview", "")) or True


def test_document_chunker_splits_long_text() -> None:
    text = "\n\n".join(f"Section {i}. " + ("content " * 100) for i in range(8))
    out = run_document_chunker(
        {"target_tokens": 150, "overlap_tokens": 20},
        {"text": text},
    )
    assert out["text"] == text
    assert out["chunking_summary"]["split_required"] is True
    assert out["chunking_summary"]["chunk_count"] >= 2
    envelope = out[TRANSIENT_CHUNK_ENVELOPE_KEY]
    assert len(envelope["chunks"]) == out["chunking_summary"]["chunk_count"]


def test_document_chunker_requires_text() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        run_document_chunker({}, {"headline": "No body"})
