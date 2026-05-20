"""Quote-safe span matching for location mention occurrences in article text."""

from __future__ import annotations

from worker.substrate_common import _WS_RE

# Private-use sentinel: map all ASCII/Unicode apostrophe and quote marks to one code point so
# `find()` indices stay aligned with the original `haystack` / `needle` (1:1 length).
_SPAN_QUOTE_SENTINEL = "\ue000"

# LLM / consolidation sometimes appends closing punctuation not present in `consolidated["text"]`.
_TRAILING_SPAN_ARTIFACT_CHARS: frozenset[str] = frozenset(
    '.,;:!?)]}"\'…\u201d\u2019\u201c'  # ASCII closers + ellipsis + curly quotes
)


def _rstrip_trailing_span_artifacts(fragment: str) -> str:
    """Drop trailing whitespace and common sentence/closing marks (iteratively)."""

    s = fragment.rstrip()
    while s and s[-1] in _TRAILING_SPAN_ARTIFACT_CHARS:
        s = s[:-1].rstrip()
    return s


def _mention_text_span_variants(needle: str) -> list[str]:
    """Longest-first candidates to search in article text (exact substring match)."""

    stripped = _rstrip_trailing_span_artifacts(needle)
    if stripped == needle:
        return [needle] if needle else []
    out: list[str] = []
    if needle:
        out.append(needle)
    if stripped:
        out.append(stripped)
    return out


def _normalize_quotes_for_span_match(text: str) -> str:
    """Unify apostrophe and quote characters without changing string length (index-safe)."""

    out: list[str] = []
    for ch in text:
        o = ord(ch)
        if ch in {'"', "'", "`"}:
            out.append(_SPAN_QUOTE_SENTINEL)
        elif ch == "\u00a0":
            out.append(" ")
        elif 0x2010 <= o <= 0x2015 or ch == "\u2212":  # hyphen / minus variants
            out.append("-")
        elif ch in "\u2018\u2019\u201a\u201b":  # single quotes
            out.append(_SPAN_QUOTE_SENTINEL)
        elif ch in "\u201c\u201d\u201e\u201f":  # double quotes
            out.append(_SPAN_QUOTE_SENTINEL)
        elif ch in "\u00ab\u00bb":  # guillemets
            out.append(_SPAN_QUOTE_SENTINEL)
        elif ch in "\u2032\u2033":  # prime / double prime
            out.append(_SPAN_QUOTE_SENTINEL)
        else:
            out.append(ch)
    return "".join(out)


def _longest_needle_substring_span(
    *, haystack: str, needle: str, min_len: int = 12
) -> tuple[int, int] | None:
    """Return the longest contiguous substring of `needle` that appears in `haystack`.

    Used when extraction wording differs from the article. Quote-normalized copies keep straight
    vs curly quotes from breaking the scan. Indices refer to the original `haystack`.
    """

    if not needle or len(needle) < min_len:
        return None

    hay_n = _normalize_quotes_for_span_match(haystack)
    need_n = _normalize_quotes_for_span_match(needle)
    if len(need_n) < min_len:
        return None

    best: tuple[int, int] | None = None
    best_len = 0
    nn = len(need_n)
    for i in range(nn):
        min_j = i + min_len
        if min_j > nn:
            continue
        for j in range(nn, min_j - 1, -1):
            sub = need_n[i:j]
            k = hay_n.find(sub)
            if k >= 0:
                span_len = j - i
                if span_len > best_len:
                    best_len = span_len
                    best = (k, k + span_len)
                break
    return best


def _find_mention_span(
    *, haystack: str, needle: str, search_from: int = 0
) -> tuple[int, int] | None:
    if not needle:
        return None
    if search_from < 0:
        search_from = 0
    if search_from >= len(haystack):
        return None

    for candidate in _mention_text_span_variants(needle):
        if not candidate:
            continue
        idx = haystack.find(candidate, search_from)
        if idx >= 0:
            return idx, idx + len(candidate)

    hay_q = _normalize_quotes_for_span_match(haystack)
    hay_q_slice = hay_q[search_from:]
    for candidate in _mention_text_span_variants(needle):
        if not candidate:
            continue
        cand_q = _normalize_quotes_for_span_match(candidate)
        idx = hay_q_slice.find(cand_q)
        if idx >= 0:
            return search_from + idx, search_from + idx + len(candidate)

    collapsed_hay = _WS_RE.sub(" ", haystack).strip()
    for candidate in _mention_text_span_variants(needle):
        if not candidate:
            continue
        collapsed_needle = _WS_RE.sub(" ", candidate).strip()
        if not collapsed_needle:
            continue
        idx2 = collapsed_hay.find(collapsed_needle)
        if idx2 >= 0:
            # Approximate mapping back to original indices by scanning for the first token.
            first_token = collapsed_needle.split(" ")[0]
            if first_token:
                idx3 = haystack.find(first_token)
                if idx3 >= 0:
                    return idx3, idx3 + len(candidate)

    collapsed_hay_q = _normalize_quotes_for_span_match(collapsed_hay)
    for candidate in _mention_text_span_variants(needle):
        if not candidate:
            continue
        collapsed_needle = _WS_RE.sub(" ", candidate).strip()
        if not collapsed_needle:
            continue
        cn_q = _normalize_quotes_for_span_match(collapsed_needle)
        idx2 = collapsed_hay_q.find(cn_q)
        if idx2 >= 0:
            first_token = collapsed_needle.split(" ")[0]
            if first_token:
                idx3 = haystack.find(first_token)
                if idx3 >= 0:
                    return idx3, idx3 + len(candidate)

    for candidate in _mention_text_span_variants(needle):
        span = _longest_needle_substring_span(haystack=haystack, needle=candidate)
        if span is not None:
            return span

    return None
