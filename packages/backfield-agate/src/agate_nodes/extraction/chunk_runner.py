"""Bounded concurrent chunk extraction with all-or-nothing failure semantics."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from agate_utils.text_chunking import DocumentChunk, DocumentChunkEnvelope

logger = logging.getLogger(__name__)

CHUNK_CALL_CONCURRENCY = 3

T = TypeVar("T")

ChunkWorker = Callable[[DocumentChunk, int], Awaitable[T]]


async def run_chunked_extraction(
    envelope: DocumentChunkEnvelope,
    worker: ChunkWorker[T],
    *,
    concurrency: int = CHUNK_CALL_CONCURRENCY,
    deadline_monotonic: float | None = None,
) -> list[T]:
    """Run ``worker`` for every chunk with bounded concurrency.

    Results are returned in chunk-index order. If any chunk fails, the error is
    raised and no partial result list is returned to the caller.
    """
    chunks = list(envelope.chunks)
    if not chunks:
        raise ValueError("Document chunk envelope contains no chunks.")

    limit = max(1, int(concurrency))
    semaphore = asyncio.Semaphore(limit)
    results: list[T | None] = [None] * len(chunks)
    errors: list[BaseException] = []

    async def _run_one(chunk: DocumentChunk) -> None:
        if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
            raise TimeoutError(
                f"Chunk {chunk.index + 1}/{len(chunks)} missed the node deadline before starting."
            )
        async with semaphore:
            if deadline_monotonic is not None and time.monotonic() >= deadline_monotonic:
                raise TimeoutError(
                    f"Chunk {chunk.index + 1}/{len(chunks)} missed the node deadline."
                )
            results[chunk.index] = await worker(chunk, len(chunks))

    tasks = [asyncio.create_task(_run_one(chunk)) for chunk in chunks]
    done = await asyncio.gather(*tasks, return_exceptions=True)
    for item in done:
        if isinstance(item, BaseException):
            errors.append(item)

    if errors:
        # Prefer the first non-cancellation failure for a clearer node error.
        primary = next(
            (err for err in errors if not isinstance(err, asyncio.CancelledError)),
            errors[0],
        )
        logger.warning(
            "Chunked extraction failed after %s chunk error(s); first=%s",
            len(errors),
            type(primary).__name__,
        )
        raise primary

    ordered: list[T] = []
    for index, value in enumerate(results):
        if value is None:
            raise RuntimeError(f"Missing result for chunk index {index}.")
        ordered.append(value)
    return ordered
