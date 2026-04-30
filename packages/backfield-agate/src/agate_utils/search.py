# tools/search.py

import requests
import logging
from typing import Any, List, Mapping, Optional, Sequence
from pydantic import BaseModel, Field
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

########## MODELS ##########

class SearchResult(BaseModel):
    """A single search result."""
    title: str = Field(description="Title of the search result")
    snippet: str = Field(description="Text snippet from the result")
    url: str = Field(description="URL of the result")
    relevance_score: float = Field(default=1.0, description="Relevance score (0-1)")


class SearchResponse(BaseModel):
    """Response from a search operation."""
    success: bool = Field(description="Whether the search was successful")
    results: List[SearchResult] = Field(default_factory=list, description="List of search results")
    query: str = Field(description="The original search query")
    error: Optional[str] = Field(default=None, description="Error message if search failed")


def _row_to_search_result(row: Mapping[str, Any], rank: int) -> SearchResult:
    """Map a provider row (Brave web result, DDG hit, etc.) to SearchResult."""
    title = str(row.get("title") or row.get("Title") or f"Result {rank + 1}")
    snippet = str(
        row.get("description")
        or row.get("snippet")
        or row.get("body")
        or row.get("Snippet")
        or ""
    )
    url = str(row.get("url") or row.get("href") or row.get("URL") or "")
    return SearchResult(
        title=title,
        snippet=snippet[:2000] if snippet else "",
        url=url,
        relevance_score=max(0.1, 1.0 - rank * 0.08),
    )


def search_response_from_rows(query: str, rows: Sequence[Mapping[str, Any]]) -> SearchResponse:
    """Build SearchResponse from normalized rows (Flowbuilder-friendly; JSON-serializable)."""
    results = [_row_to_search_result(r, i) for i, r in enumerate(rows)]
    return SearchResponse(success=True, results=results, query=query)


########## BRAVE LLM CONTEXT ##########

def brave_llm_context_raw(
    query: str,
    api_key: str,
    *,
    count: int = 5,
    maximum_number_of_tokens: int = 8192,
    maximum_number_of_urls: int = 20,
    maximum_number_of_snippets: int = 50,
    context_threshold_mode: str = "balanced",
    timeout: float = 30.0,
    **kwargs: Any,
) -> dict | None:
    """
    Brave LLM Context API: pre-extracted web content for LLM grounding / RAG.

    GET https://api.search.brave.com/res/v1/llm/context
    Returns full JSON: grounding.generic (url, title, snippets[]), sources.

    Args:
        query: Search query (1–400 chars, max 50 words).
        api_key: Brave API key (X-Subscription-Token).
        count: Max search results to consider (1–50).
        maximum_number_of_tokens: Approx max tokens in context (1024–32768).
        maximum_number_of_urls: Max URLs in response (1–50).
        maximum_number_of_snippets: Max snippets across all URLs (1–100).
        context_threshold_mode: strict | balanced | lenient | disabled.
        timeout: Request timeout seconds.
        **kwargs: Passed as query params (e.g. country, search_lang, freshness).

    Returns:
        Full API response dict, or None on failure.
    """
    try:
        if not api_key:
            logger.error("Brave API key not provided for LLM context")
            return None
        q = (query or "").strip()
        if not q:
            logger.error("Empty query for Brave LLM context")
            return None

        url = "https://api.search.brave.com/res/v1/llm/context"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }
        params: dict[str, Any] = {
            "q": q[:400],
            "count": max(1, min(count, 50)),
            "maximum_number_of_tokens": max(1024, min(maximum_number_of_tokens, 32768)),
            "maximum_number_of_urls": max(1, min(maximum_number_of_urls, 50)),
            "maximum_number_of_snippets": max(1, min(maximum_number_of_snippets, 100)),
            "context_threshold_mode": context_threshold_mode,
            **kwargs,
        }
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error("Brave LLM context request failed: %s", e)
        return None


def brave_llm_context_text(
    query: str,
    api_key: str,
    *,
    max_chars: int = 12000,
    count: int = 5,
    maximum_number_of_tokens: int = 8192,
    maximum_number_of_urls: int = 20,
    context_threshold_mode: str = "balanced",
    timeout: float = 30.0,
    **kwargs: Any,
) -> str:
    """
    Brave LLM Context as a single string for prompt injection.

    Calls brave_llm_context_raw and concatenates grounding.generic (title + snippets)
    up to max_chars. Useful for agents and RAG pipelines.

    Returns:
        Concatenated context string, or "" on failure/empty.
    """
    raw = brave_llm_context_raw(
        query,
        api_key,
        count=count,
        maximum_number_of_tokens=maximum_number_of_tokens,
        maximum_number_of_urls=maximum_number_of_urls,
        context_threshold_mode=context_threshold_mode,
        timeout=timeout,
        **kwargs,
    )
    if not raw:
        return ""
    generic = (raw.get("grounding") or {}).get("generic") or []
    if not generic:
        return ""
    parts: list[str] = []
    n = 0
    for item in generic:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        snippets = item.get("snippets") or []
        block = f"[{title}]\n" + "\n".join(str(s).strip() for s in snippets if s)
        if block.strip():
            parts.append(block)
            n += len(block) + 1
            if n >= max_chars:
                break
    out = "\n\n".join(parts)
    if len(out) > max_chars:
        out = out[: max_chars - 3] + "..."
    return out


def brave_llm_context(
    query: str,
    api_key: str,
    *,
    count: int = 5,
    maximum_number_of_tokens: int = 8192,
    maximum_number_of_urls: int = 20,
    maximum_number_of_snippets: int = 50,
    context_threshold_mode: str = "balanced",
    timeout: float = 30.0,
    **kwargs: Any,
) -> SearchResponse:
    """
    Brave LLM Context API returning SearchResponse (same contract as other search functions).

    Calls brave_llm_context_raw and maps grounding.generic to SearchResult (title, snippet, url).
    """
    q = (query or "").strip()
    if not q:
        return SearchResponse(success=False, error="Empty query", results=[], query=query)
    if not api_key:
        return SearchResponse(
            success=False,
            error="Brave API key not provided",
            results=[],
            query=q,
        )
    raw = brave_llm_context_raw(
        query,
        api_key,
        count=count,
        maximum_number_of_tokens=maximum_number_of_tokens,
        maximum_number_of_urls=maximum_number_of_urls,
        maximum_number_of_snippets=maximum_number_of_snippets,
        context_threshold_mode=context_threshold_mode,
        timeout=timeout,
        **kwargs,
    )
    if not raw:
        return SearchResponse(
            success=False,
            error="Brave LLM context request failed",
            results=[],
            query=q,
        )
    generic = (raw.get("grounding") or {}).get("generic") or []
    rows: list[dict[str, Any]] = []
    for item in generic:
        if not isinstance(item, dict):
            continue
        snippets = item.get("snippets") or []
        body = "\n".join(str(s).strip() for s in snippets if s)
        rows.append({
            "title": item.get("title") or "",
            "description": body[:2000],
            "url": item.get("url") or "",
        })
    return search_response_from_rows(q, rows)


def brave_place_search_raw(
    api_key: str,
    *,
    q: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    location: str | None = None,
    radius: float | None = None,
    count: int = 20,
    timeout: float = 30.0,
    **kwargs: Any,
) -> dict | None:
    """
    Brave Place Search API: find geographic places (businesses, landmarks, POIs).

    GET https://api.search.brave.com/res/v1/local/place_search
    Returns full JSON: type "locations", results[], query, location (when geo provided).

    Provide either (latitude + longitude) or location for best results; omit for
    broader global search. Omit q for "explore mode" (general POIs in the area).

    Args:
        api_key: Brave API key (X-Subscription-Token).
        q: Search query (e.g. "coffee shops", "museums"). Omit for area exploration.
        latitude: Latitude of search center (-90 to 90). Use with longitude.
        longitude: Longitude of search center (-180 to 180). Use with latitude.
        location: Location name instead of coordinates (e.g. "san francisco ca united states").
        radius: Search radius in meters (optional; tighter = more focused results).
        count: Number of results (1–50).
        timeout: Request timeout seconds.
        **kwargs: Passed as query params (e.g. country, search_lang, units, safesearch).

    Returns:
        Full API response dict, or None on failure.
    """
    try:
        if not api_key:
            logger.error("Brave API key not provided for place search")
            return None

        url = "https://api.search.brave.com/res/v1/local/place_search"
        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        }
        params: dict[str, Any] = {
            "count": max(1, min(count, 50)),
            **kwargs,
        }
        if q is not None and str(q).strip():
            params["q"] = str(q).strip()[:400]
        if latitude is not None and longitude is not None:
            params["latitude"] = latitude
            params["longitude"] = longitude
        elif location is not None and str(location).strip():
            params["location"] = str(location).strip()
        if radius is not None:
            params["radius"] = radius

        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error("Brave place search request failed: %s", e)
        return None


def brave_place_search(
    api_key: str,
    *,
    q: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    location: str | None = None,
    radius: float | None = None,
    count: int = 20,
    timeout: float = 30.0,
    **kwargs: Any,
) -> SearchResponse:
    """
    Brave Place Search API returning SearchResponse (same contract as other search functions).

    Calls brave_place_search_raw and maps results[] to SearchResult (title, snippet, url).
    Snippet uses description or postal_address.displayAddress when available.
    """
    if not api_key:
        query_label = (q or location or "place search") or "place search"
        return SearchResponse(
            success=False,
            error="Brave API key not provided",
            results=[],
            query=query_label,
        )
    raw = brave_place_search_raw(
        api_key,
        q=q,
        latitude=latitude,
        longitude=longitude,
        location=location,
        radius=radius,
        count=count,
        timeout=timeout,
        **kwargs,
    )
    query_label = (q or "").strip() or (location or "").strip() or (
        f"{latitude},{longitude}" if latitude is not None and longitude is not None else "place search"
    )
    if not raw:
        return SearchResponse(
            success=False,
            error="Brave place search request failed",
            results=[],
            query=query_label,
        )
    results_list = raw.get("results") or []
    rows: list[dict[str, Any]] = []
    for item in results_list:
        if not isinstance(item, dict):
            continue
        addr = (item.get("postal_address") or {}) if isinstance(item.get("postal_address"), dict) else {}
        snippet = str(item.get("description") or "").strip() or str(addr.get("displayAddress") or "").strip()
        rows.append({
            "title": item.get("title") or "",
            "description": snippet[:2000],
            "url": item.get("url") or "",
        })
    return search_response_from_rows(query_label, rows)


########## DUCKDUCKGO (no API key; Flowbuilder-ready SearchResponse) ##########


def search_web_duckduckgo(
    query: str,
    max_results: int = 10,
    timeout: Optional[float] = 15.0,
) -> SearchResponse:
    """
    Web search via DuckDuckGo (no API key). Returns SearchResponse for agents and Flowbuilder nodes.

    Note: duckduckgo_search's public ``text()`` currently forces a Bing-only path that often
    returns no results from servers. We prefer DDG lite (and html) backends first.

    Args:
        query: Search string.
        max_results: Max hits (capped for stability).
        timeout: HTTP timeout seconds; None uses library default (10).

    Returns:
        SearchResponse: success=False + error on total failure; success=True with zero
        results if every backend returned empty.
    """
    q = (query or "").strip()
    if not q:
        return SearchResponse(success=False, error="Empty query", results=[], query=query)

    # Lite POST payload behaves better with bounded query length
    q_search = q if len(q) <= 400 else q[:397] + "..."
    max_results = max(1, min(max_results, 25))
    to = int(timeout) if timeout is not None else 10

    rows: list[dict[str, Any]] = []
    last_err: Optional[str] = None

    try:
        with DDGS(timeout=to) as ddgs:
            # 1) Lite — reliable from most networks (library's text() skips this today)
            try:
                rows = list(ddgs._text_lite(q_search, max_results=max_results))  # type: ignore[attr-defined]
            except Exception as ex:
                last_err = str(ex)
                logger.info("DuckDuckGo lite backend: %s", ex)
                rows = []

            # 2) HTML backend
            if len(rows) < max_results:
                try:
                    more = ddgs._text_html(q_search, max_results=max_results)  # type: ignore[attr-defined]
                    seen = {r.get("href") for r in rows if r.get("href")}
                    for r in more or []:
                        if not isinstance(r, dict):
                            continue
                        h = r.get("href")
                        if h and h in seen:
                            continue
                        if h:
                            seen.add(h)
                        rows.append(r)
                        if len(rows) >= max_results:
                            break
                except Exception as ex:
                    last_err = last_err or str(ex)
                    logger.info("DuckDuckGo html backend: %s", ex)

            # 3) Public text() (Bing-only in recent package versions)
            if not rows:
                try:
                    rows = ddgs.text(q_search, max_results=max_results) or []
                except Exception as ex:
                    last_err = str(ex)
                    logger.info("DuckDuckGo text()/bing: %s", ex)
                    rows = []

        if not rows and last_err:
            return SearchResponse(success=False, error=last_err, results=[], query=q)
        return search_response_from_rows(q, rows)
    except Exception as e:
        logger.error("DuckDuckGo search failed: %s", e)
        return SearchResponse(
            success=False,
            error=str(e),
            results=[],
            query=q,
        )