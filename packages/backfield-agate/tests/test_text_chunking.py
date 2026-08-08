"""Tests for deterministic document chunking."""

from __future__ import annotations

import pytest
from agate_utils.text_chunking import (
    MAX_CHUNKS,
    approximate_token_count,
    single_chunk_envelope,
    split_document_text,
    truncate_text_to_tokens,
)


def test_short_document_is_single_chunk() -> None:
    envelope = split_document_text("Short story.", target_tokens=4000, overlap_tokens=250)
    assert envelope.split_required is False
    assert len(envelope.chunks) == 1
    assert envelope.chunks[0].text == "Short story."
    assert envelope.chunks[0].ownership_start == 0
    assert envelope.chunks[0].ownership_end == len("Short story.")


def test_ownership_covers_full_document_without_gaps() -> None:
    paragraphs = [f"Paragraph {i}. " + ("word " * 80) for i in range(12)]
    text = "\n\n".join(paragraphs)
    envelope = split_document_text(text, target_tokens=200, overlap_tokens=20)
    assert envelope.split_required is True
    assert len(envelope.chunks) >= 2
    covered = 0
    for chunk in envelope.chunks:
        assert chunk.ownership_start == covered
        assert chunk.context_start <= chunk.ownership_start
        assert chunk.ownership_end <= chunk.context_end
        assert chunk.text == text[chunk.context_start : chunk.context_end]
        covered = chunk.ownership_end
    assert covered == len(text)


def test_overlap_adds_context_without_ownership_overlap() -> None:
    text = (
        ("Sentence one. " * 40)
        + "\n\n"
        + ("Sentence two. " * 40)
        + "\n\n"
        + ("Sentence three. " * 40)
    )
    envelope = split_document_text(text, target_tokens=80, overlap_tokens=20)
    assert len(envelope.chunks) >= 2
    for left, right in zip(envelope.chunks, envelope.chunks[1:], strict=False):
        assert left.ownership_end == right.ownership_start
        assert right.context_start <= right.ownership_start
        if right.ownership_start > 0 and envelope.overlap_tokens > 0:
            assert right.context_start < right.ownership_start


def test_max_chunks_rejected() -> None:
    # Force many tiny ownership windows.
    text = "\n\n".join(f"Block {i}. " + ("x " * 30) for i in range(MAX_CHUNKS + 5))
    with pytest.raises(ValueError, match="maximum"):
        split_document_text(text, target_tokens=20, overlap_tokens=2)


def test_truncate_prefers_paragraph_boundary() -> None:
    text = ("A" * 100) + "\n\n" + ("B" * 500)
    truncated, was = truncate_text_to_tokens(text, max_tokens=40)
    assert was is True
    assert "\n\n" not in truncated or truncated.endswith("A" * 100) or truncated.endswith("A")
    assert approximate_token_count(truncated) <= 40


def test_single_chunk_envelope() -> None:
    envelope = single_chunk_envelope("Hello world")
    assert len(envelope.chunks) == 1
    assert envelope.split_required is False
