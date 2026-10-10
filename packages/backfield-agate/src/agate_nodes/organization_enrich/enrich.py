"""Attach accepted Wikidata and Wikipedia links to organizations."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import httpx

from agate_nodes.organization_enrich.params import (
    WIKIDATA_SOURCE,
    WIKIPEDIA_SOURCE,
    OrganizationEnrichParams,
)
from agate_nodes.organization_enrich.remote import (
    RECON_BATCH_SIZE,
    choose_wikidata_match,
    english_wikipedia_urls,
    http_client,
    reconcile_batch,
)

logger = logging.getLogger(__name__)

MISSING_MODEL_WARNING = "Choose a decision model before enrichment can run."
MISSING_CREDENTIAL_WARNING = "Add a saved key for the decision model before enrichment can run."
MISSING_SOURCES_WARNING = "Choose Wikidata, Wikipedia, or both before enrichment can run."
PARTIAL_FAILURE_WARNING = "Some organizations could not be matched and were left unchanged."

CacheLookup = Callable[[dict[str, Any]], dict[str, str] | None]


def enrich_organizations(
    organizations: list[Any],
    settings: OrganizationEnrichParams,
    *,
    litellm_model: str,
    api_key: str | None,
    api_base: str | None,
    cached_links: CacheLookup,
    system_prompt: str | None = None,
    client: httpx.Client | None = None,
) -> tuple[list[Any], list[str]]:
    """Return organizations with accepted links and any warnings. Failures leave one unchanged."""
    copied: list[Any] = [
        dict(organization) if isinstance(organization, dict) else organization
        for organization in organizations
    ]
    sources = settings.selected_sources()
    if not sources:
        return copied, [MISSING_SOURCES_WARNING]
    eligible = [
        index for index, organization in enumerate(copied) if isinstance(organization, dict)
    ]
    if not eligible:
        return copied, []
    if not (settings.ai_model_config_id or "").strip():
        return copied, [MISSING_MODEL_WARNING]
    if not (api_key or "").strip() or not (litellm_model or "").strip():
        return copied, [MISSING_CREDENTIAL_WARNING]

    needs_lookup: list[int] = []
    for index in eligible:
        organization = copied[index]
        assert isinstance(organization, dict)
        cached = _safe_cache(cached_links, organization)
        if cached:
            _apply_links(organization, cached, sources)
            continue
        needs_lookup.append(index)
    if not needs_lookup:
        return copied, []

    owns_client = client is None
    http = client if client is not None else http_client()
    try:
        accepted, had_failure = _choose_matches(
            http,
            copied,
            needs_lookup,
            settings,
            litellm_model=litellm_model,
            api_key=api_key or "",
            api_base=api_base,
            system_prompt=system_prompt,
        )
        wiki_urls: dict[str, str] = {}
        if WIKIPEDIA_SOURCE in sources and accepted:
            try:
                wiki_urls = english_wikipedia_urls(http, list(accepted.values()))
            except Exception:
                logger.warning("Wikipedia sitelink lookup failed", exc_info=True)
                had_failure = True
                wiki_urls = {}
        for index, qid in accepted.items():
            organization = copied[index]
            if not isinstance(organization, dict):
                continue
            links: dict[str, str] = {}
            if WIKIDATA_SOURCE in sources:
                links["wikidata_id"] = qid
            if WIKIPEDIA_SOURCE in sources and wiki_urls.get(qid):
                links["wikipedia_url"] = wiki_urls[qid]
            if links:
                _apply_links(organization, links, sources)
    finally:
        if owns_client:
            http.close()

    warnings = [PARTIAL_FAILURE_WARNING] if had_failure else []
    return copied, warnings


def _safe_cache(cached_links: CacheLookup, organization: dict[str, Any]) -> dict[str, str] | None:
    try:
        return cached_links(organization)
    except Exception:
        logger.warning("Organization enrichment cache lookup failed", exc_info=True)
        return None


def _choose_matches(
    client: httpx.Client,
    organizations: list[Any],
    indexes: list[int],
    settings: OrganizationEnrichParams,
    *,
    litellm_model: str,
    api_key: str,
    api_base: str | None,
    system_prompt: str | None,
) -> tuple[dict[int, str], bool]:
    candidates_by_index: dict[int, list[dict[str, str]]] = {}
    had_failure = False
    for start in range(0, len(indexes), RECON_BATCH_SIZE):
        batch = indexes[start : start + RECON_BATCH_SIZE]
        batch_organizations = [
            organizations[index] for index in batch if isinstance(organizations[index], dict)
        ]
        if len(batch_organizations) != len(batch):
            continue
        try:
            aligned = reconcile_batch(client, batch_organizations)
        except Exception:
            logger.warning("Wikidata reconciliation failed", exc_info=True)
            had_failure = True
            continue
        for index, candidates in zip(batch, aligned, strict=True):
            candidates_by_index[index] = candidates

    accepted: dict[int, str] = {}
    for index, candidates in candidates_by_index.items():
        if not candidates:
            continue
        organization = organizations[index]
        if not isinstance(organization, dict):
            continue
        try:
            choice, confidence = choose_wikidata_match(
                client,
                api_key=api_key,
                api_base=api_base,
                litellm_model=litellm_model,
                model_config_id=settings.ai_model_config_id,
                organization=organization,
                candidates=candidates,
                system_prompt=system_prompt,
            )
        except Exception:
            logger.warning("Decision model match failed", exc_info=True)
            had_failure = True
            continue
        if choice is None or confidence is None or confidence < settings.confidence_cutoff:
            continue
        accepted[index] = choice
    return accepted, had_failure


def _apply_links(organization: dict[str, Any], links: dict[str, str], sources: set[str]) -> None:
    if WIKIDATA_SOURCE in sources:
        qid = links.get("wikidata_id")
        if isinstance(qid, str) and qid.strip():
            organization["wikidata_id"] = qid.strip()
    if WIKIPEDIA_SOURCE in sources:
        url = links.get("wikipedia_url")
        if isinstance(url, str) and url.strip():
            organization["wikipedia_url"] = url.strip()
