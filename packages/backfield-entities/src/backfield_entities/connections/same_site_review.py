"""Focused LLM review for unresolved same-site org→location hints."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from backfield_entities.connections.same_site_hints import SameSiteOrgLocationHint
from backfield_entities.connections.snippets import collect_pair_snippets_for_entities
from backfield_entities.connections.types import AutoConnectionEdgeProposal

logger = logging.getLogger(__name__)

AUTO_CONNECTION_SAME_SITE_PAIR_PROMPT_VERSION = "auto_connections_same_site_pair_v1"


def build_same_site_pair_review_prompt(
    *,
    hint: SameSiteOrgLocationHint,
    pair_snippets: tuple[str, ...],
) -> str:
    snippet_section = (
        "\n".join(f'- "{snippet}"' for snippet in pair_snippets) if pair_snippets else "(none)"
    )
    return (
        f"prompt_version: {AUTO_CONNECTION_SAME_SITE_PAIR_PROMPT_VERSION}\n"
        "Decide whether the organization is physically located at the place canonical "
        "(located_at), using ONLY the evidence below.\n\n"
        f"Organization: id={hint.org.canonical_id} label={hint.org.label!r} "
        f"organization_type={hint.org.organization_type!r}\n"
        f"Location: id={hint.location.canonical_id} label={hint.location.label!r} "
        f"location_type={hint.location.location_type!r}\n"
        f"Name match basis: {hint.match_basis}\n\n"
        "Rules:\n"
        "- Return link=true only when the text explicitly places the organization at this "
        "site (not merely a parent district, city, or nearby geography).\n"
        "- The quote must be copied from the snippets.\n"
        "- confidence must be >= 0.9 only when you would publish this link.\n"
        "- Prefer link=false over a stretched association.\n\n"
        f"Evidence snippets:\n{snippet_section}\n\n"
        'Return JSON only: {"link": true|false, "nature": "located_at", '
        '"confidence": 0.95, "quote": "...", "reason": "..."}'
    )


def review_same_site_org_location_pair(
    *,
    hint: SameSiteOrgLocationHint,
    article_text: str,
    model: str,
    model_config_id: str | None,
    call_llm: Callable[..., str],
) -> AutoConnectionEdgeProposal | None:
    """Run a focused LLM review for one hinted org→location pair."""
    pair_snippets = hint.suggested_snippets or collect_pair_snippets_for_entities(
        left=hint.org,
        right=hint.location,
        article_text=article_text,
    )
    if not pair_snippets:
        return None

    prompt = build_same_site_pair_review_prompt(hint=hint, pair_snippets=pair_snippets)
    try:
        raw = call_llm(
            prompt,
            model=model,
            force_json=True,
            temperature=0.0,
            max_tokens=500,
            model_config_id=model_config_id,
        )
        data = json.loads(raw)
    except Exception as exc:
        logger.warning(
            "Same-site pair review LLM failed for %s -> %s: %s",
            hint.org.canonical_id,
            hint.location.canonical_id,
            exc,
        )
        return None

    if not isinstance(data, dict) or not data.get("link"):
        return None

    quote = str(data.get("quote") or "").strip()
    if not quote:
        return None
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0

    nature = str(data.get("nature") or "located_at").strip().lower() or "located_at"
    reason = str(data.get("reason") or "").strip() or "Same-site org→location review."

    return AutoConnectionEdgeProposal(
        from_entity_id=hint.org.canonical_id,
        to_entity_id=hint.location.canonical_id,
        nature=nature,
        confidence=confidence,
        quote=quote,
        reason=reason,
        match_basis=hint.match_basis,
        prompt_version=AUTO_CONNECTION_SAME_SITE_PAIR_PROMPT_VERSION,
    )
