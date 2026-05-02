"""LLM-backed ``location`` display line for consolidated geocode output (with heuristic fallback)."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import string
from pathlib import Path

from agate_utils.llm import call_llm

from ..types import AgentState

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "location_display_format.md"

_TRAIL_US = re.compile(
    r",\s*(US|USA|United States)\s*$",
    re.IGNORECASE,
)

# US states + DC (two-letter postal abbreviations).
_US_STATE_ABBR: frozenset[str] = frozenset(
    {
        "AL",
        "AK",
        "AZ",
        "AR",
        "CA",
        "CO",
        "CT",
        "DE",
        "DC",
        "FL",
        "GA",
        "HI",
        "ID",
        "IL",
        "IN",
        "IA",
        "KS",
        "KY",
        "LA",
        "ME",
        "MD",
        "MA",
        "MI",
        "MN",
        "MS",
        "MO",
        "MT",
        "NE",
        "NV",
        "NH",
        "NJ",
        "NM",
        "NY",
        "NC",
        "ND",
        "OH",
        "OK",
        "OR",
        "PA",
        "RI",
        "SC",
        "SD",
        "TN",
        "TX",
        "UT",
        "VT",
        "VA",
        "WA",
        "WV",
        "WI",
        "WY",
    }
)


def _title_segment_words(seg: str) -> str:
    """Title-case words in one segment; preserve hyphenated names."""
    seg = seg.strip()
    if not seg:
        return seg
    if "-" in seg:
        return "-".join(_title_segment_words(part) for part in seg.split("-"))
    return string.capwords(seg)


def apply_title_case_location_line(line: str) -> str:
    """
    Title-case place names by comma segment; uppercase US state 2-letter codes.

    Trailing ``US`` (country) after a comma is kept as uppercase ``US``.
    """
    s = (line or "").strip()
    if not s:
        return s
    raw_parts = [p.strip() for p in s.split(",")]
    parts: list[str] = [p for p in raw_parts if p]
    if not parts:
        return s
    out: list[str] = []
    for i, part in enumerate(parts):
        is_last = i == len(parts) - 1
        if re.fullmatch(r"[A-Za-z]{2}", part) and part.upper() in _US_STATE_ABBR:
            out.append(part.upper())
        elif is_last and part.upper() == "US":
            out.append("US")
        else:
            out.append(_title_segment_words(part))
    return ", ".join(out)


def _heuristic_emit_location(
    location_type: str,
    location_text: str,
    formatted_address: str,
) -> str:
    """Cheap fallback when LLM is skipped or fails."""
    lt = (location_type or "").lower()
    base = (location_text or "").strip() or (formatted_address or "").strip()
    out = base
    if lt != "region_country" and out:
        out = _TRAIL_US.sub("", out).rstrip().rstrip(",").strip()
    if lt == "region_country" and out:
        out = re.sub(r"\bUSA\b", "US", out)
    return apply_title_case_location_line(out)


async def compute_emit_location_line(
    state: AgentState,
    *,
    formatted_address: str,
) -> str:
    """
    Produce the human-facing ``location`` string for a geocoded item.

    Uses a small JSON LLM when ``openai_api_key`` is set; otherwise heuristics on ``location_text``.
    """
    location_type = (state.get("location_type") or "").strip()
    location_text = (state.get("location_text") or "").strip()
    formatted_address = (formatted_address or "").strip()
    openai_key = state.get("openai_api_key")
    model = (
        state.get("evaluation_llm_model")
        or state.get("router_llm_model")
        or "gpt-5-nano"
    )
    components = state.get("location_components") or {}
    if not isinstance(components, dict):
        components = {}
    components_json = json.dumps(components, default=str, ensure_ascii=False)[:2000]

    if not openai_key:
        return _heuristic_emit_location(location_type, location_text, formatted_address)

    try:
        rules = _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("location_display_format prompt missing: %s", exc)
        return _heuristic_emit_location(location_type, location_text, formatted_address)

    user_block = (
        f"type: {location_type}\n"
        f"q: {location_text}\n"
        f"formatted_address: {formatted_address}\n"
        f"components_json: {components_json}\n"
    )
    prompt = f"{rules}\n---\n{user_block}"

    def _sync() -> str:
        return call_llm(
            prompt,
            model,
            None,
            True,
            1,
            0.0,
            512,
            openai_key,
            None,
            None,
            45.0,
        )

    try:
        raw = await asyncio.to_thread(_sync)
        payload = json.loads(raw)
    except Exception as exc:
        logger.debug("emit_location_line LLM failed, using heuristic: %s", exc)
        return _heuristic_emit_location(location_type, location_text, formatted_address)

    loc = payload.get("location") if isinstance(payload, dict) else None
    if not isinstance(loc, str):
        return _heuristic_emit_location(location_type, location_text, formatted_address)
    loc = loc.strip()
    if not loc:
        return _heuristic_emit_location(location_type, location_text, formatted_address)
    return apply_title_case_location_line(loc)
