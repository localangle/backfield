"""Generic chunked extraction loop used by person/org/place/custom extract nodes."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Any

from agate_runtime.context import AgateEnvContext
from agate_utils.llm import call_llm
from agate_utils.text_chunking import (
    TRANSIENT_CHUNK_ENVELOPE_KEY,
    DocumentChunk,
    DocumentChunkEnvelope,
)
from backfield_ai.prompt_budget import assert_prompt_fits

from agate_nodes.extraction.chunk_runner import run_chunked_extraction
from agate_nodes.extraction.grounding import (
    ChunkCandidate,
    locate_evidence_span,
    mark_ownership,
)
from agate_nodes.extraction.prompt_text import (
    apply_chunk_text_to_flattened,
    build_chunk_analysis_text,
)
from agate_nodes.extraction.shared_llm import (
    model_config_id_from_params,
    node_deadline_monotonic,
)

logger = logging.getLogger(__name__)

ParseChunkFn = Callable[[Any, DocumentChunk, str], list[ChunkCandidate[dict[str, Any]]]]
BuildPromptFn = Callable[[dict[str, Any]], str]
StitchFn = Callable[
    [list[ChunkCandidate[dict[str, Any]]]],
    tuple[list[dict[str, Any]], int],
]


async def extract_entities_over_chunks(
    *,
    envelope: DocumentChunkEnvelope,
    flattened: dict[str, Any],
    params: Any,
    ctx: AgateEnvContext,
    start_time: float,
    system_message: str,
    log_label: str,
    build_prompt: BuildPromptFn,
    parse_chunk_response: ParseChunkFn,
    stitch: StitchFn,
    resolved_model: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run bounded concurrent chunk extraction and stitch owned candidates."""
    model_config_id = model_config_id_from_params(params)
    deadline = node_deadline_monotonic(start_time)
    llm_timeout_cap = float(getattr(params, "llmTimeout", 600) or 600)

    async def worker(
        chunk: DocumentChunk,
        chunk_count: int,
    ) -> list[ChunkCandidate[dict[str, Any]]]:
        remaining = max(60.0, deadline - time.monotonic())
        timeout = min(llm_timeout_cap, remaining)
        chunk_text = build_chunk_analysis_text(chunk, envelope.text)
        prompt_state = apply_chunk_text_to_flattened(flattened, chunk_text=chunk_text)
        # Keep original full text available only via envelope; prompts use chunk text.
        prompt = build_prompt(prompt_state)
        merged_system = system_message
        if ctx.project_system_prompt:
            merged_system = f"{system_message}\n\n{ctx.project_system_prompt}"
        assert_prompt_fits(
            litellm_model=resolved_model,
            system_message=merged_system,
            user_prompt=prompt,
            chunker_guidance=False,
        )
        logger.info(
            "[%s] chunk LLM call index=%s/%s timeout_s=%.1f prompt_chars=%d",
            log_label,
            chunk.index + 1,
            chunk_count,
            timeout,
            len(prompt),
        )
        try:
            response_text = await asyncio.wait_for(
                asyncio.to_thread(
                    call_llm,
                    prompt=prompt,
                    model=resolved_model,
                    system_message=system_message,
                    force_json=True,
                    temperature=0.0,
                    timeout=timeout,
                    openai_api_key=ctx.get_api_key("OPENAI_API_KEY"),
                    anthropic_api_key=ctx.get_api_key("ANTHROPIC_API_KEY"),
                    gemini_api_key=ctx.get_api_key("GEMINI_API_KEY"),
                    openrouter_api_key=ctx.get_api_key("OPENROUTER_API_KEY"),
                    azure_api_key=ctx.get_api_key("AZURE_API_KEY"),
                    azure_api_base=ctx.get_api_key("AZURE_API_BASE"),
                    project_system_prompt=ctx.project_system_prompt,
                    model_config_id=model_config_id,
                ),
                timeout=timeout,
            )
        except TimeoutError as exc:
            raise TimeoutError(
                f"{log_label} chunk {chunk.index + 1}/{chunk_count} exceeded timeout "
                f"of {timeout:.0f}s"
            ) from exc

        try:
            response_data = json.loads(response_text)
        except json.JSONDecodeError as exc:
            preview = (response_text or "")[:800]
            raise ValueError(
                f"{log_label} chunk {chunk.index + 1} returned invalid JSON: {exc}. "
                f"Preview: {preview!r}"
            ) from exc

        return parse_chunk_response(response_data, chunk, envelope.text)

    per_chunk = await run_chunked_extraction(
        envelope,
        worker,
        deadline_monotonic=deadline,
    )
    candidates: list[ChunkCandidate[dict[str, Any]]] = []
    for group in per_chunk:
        candidates.extend(group)

    entities, unresolved = stitch(candidates)
    diagnostics = {
        "chunk_count": len(envelope.chunks),
        "candidate_count": len(candidates),
        "owned_candidate_count": sum(1 for c in candidates if c.owned),
        "unresolved_abbreviations": unresolved,
    }
    return entities, diagnostics


def strip_transient_chunk_keys(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove transient chunk envelope keys from a node output dict."""
    out = dict(payload)
    out.pop(TRANSIENT_CHUNK_ENVELOPE_KEY, None)
    return out


def evidence_from_person_or_org(
    entry: dict[str, Any],
    *,
    source_text: str,
    chunk: DocumentChunk,
) -> ChunkCandidate[dict[str, Any]]:
    """Build a grounded candidate using extras.ea, first mention, or name."""
    extras = entry.get("extras") if isinstance(entry.get("extras"), dict) else {}
    evidence_text = ""
    if isinstance(extras, dict):
        raw_ea = extras.get("ea") or extras.get("evidence_anchor")
        if isinstance(raw_ea, str):
            evidence_text = raw_ea.strip()
    if not evidence_text:
        mentions = entry.get("mentions") or []
        if isinstance(mentions, list) and mentions:
            first = mentions[0]
            if isinstance(first, dict) and isinstance(first.get("text"), str):
                evidence_text = first["text"].strip()
            elif isinstance(first, list) and first:
                evidence_text = str(first[0]).strip()
    if not evidence_text:
        evidence_text = str(entry.get("name") or entry.get("location") or "").strip()

    span = locate_evidence_span(
        source_text=source_text,
        chunk=chunk,
        evidence_text=evidence_text,
        prefer_owned=True,
    )
    # Drop internal extras from public payload copies when present.
    payload = {k: v for k, v in entry.items() if k != "extras"}
    if "extras" in entry and isinstance(entry["extras"], dict):
        cleaned_extras = {
            k: v
            for k, v in entry["extras"].items()
            if k not in {"ea", "evidence_anchor"}
        }
        if cleaned_extras:
            # Keep non-evidence extras by folding known fields already expanded elsewhere.
            pass
    candidate = ChunkCandidate(
        payload=payload,
        chunk_index=chunk.index,
        evidence=span,
    )
    return mark_ownership(candidate, chunk=chunk)
