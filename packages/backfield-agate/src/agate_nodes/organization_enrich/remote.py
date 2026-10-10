"""Wikidata reconciliation, Jev choice, and English Wikipedia sitelinks."""

from __future__ import annotations

import json
import logging
import time
from decimal import Decimal
from typing import Any
from urllib.parse import quote

import httpx
from agate_utils.llm import merge_system_messages
from backfield_ai.constants import AI_MODEL_KIND_DECISION
from backfield_ai.tracking_context import persist_llm_attempt

logger = logging.getLogger(__name__)

USER_AGENT = "BackfieldOrganizationEnrich/1.0 (https://www.backfield.news; organization-enrich)"
RECONCILE_URL = "https://wikidata-reconciliation.wmcloud.org/en/api"
WIKIDATA_API_URL = "https://www.wikidata.org/w/api.php"
TYPESAFE_DEFAULT_BASE = "https://api.typesafe.ai"
RECON_BATCH_SIZE = 8
WIKIDATA_ENTITY_BATCH = 50
ORGANIZATION_TYPE_QID = "Q43229"

_CHOICE_INSTRUCTIONS = (
    "Choose the Wikidata item that is the same organization as the record. "
    "Choose none when no candidate is clearly the same organization."
)
_NONE_CRITERION = "None of these candidates is the same organization."


def http_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
        headers={"User-Agent": USER_AGENT},
    )


def jev_model_name(litellm_model: str) -> str:
    name = (litellm_model or "").strip()
    if name.startswith("typesafe/"):
        name = name[len("typesafe/") :]
    return name


def reconcile_batch(
    client: httpx.Client,
    organizations: list[dict[str, Any]],
) -> list[list[dict[str, str]]]:
    """Return candidate lists aligned with ``organizations``. Each has id, name, description."""
    queries: dict[str, dict[str, Any]] = {}
    for index, organization in enumerate(organizations):
        name = _query_name(organization)
        if not name:
            continue
        queries[str(index)] = {
            "query": name,
            "type": ORGANIZATION_TYPE_QID,
            "type_strict": "should",
            "limit": 5,
        }
    if not queries:
        return [[] for _ in organizations]
    response = client.post(RECONCILE_URL, data={"queries": json.dumps(queries)})
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Wikidata reconciliation returned an unexpected response")
    aligned: list[list[dict[str, str]]] = []
    for index in range(len(organizations)):
        block = payload.get(str(index))
        aligned.append(_candidates_from_block(block))
    return aligned


def choose_wikidata_match(
    client: httpx.Client,
    *,
    api_key: str,
    api_base: str | None,
    litellm_model: str,
    model_config_id: str | None,
    organization: dict[str, Any],
    candidates: list[dict[str, str]],
    system_prompt: str | None,
) -> tuple[str | None, float | None]:
    """Ask the decision model which candidate is the organization. ``none`` means no match."""
    model_name = jev_model_name(litellm_model)
    criteria = _choice_criteria(candidates)
    state = _decision_state(organization, candidates)
    body = {
        "model": model_name,
        "state": state,
        "questions": {
            "match": {
                "type": "choice",
                "instructions": merge_system_messages(
                    _CHOICE_INSTRUCTIONS,
                    system_prompt,
                    force_json=False,
                ),
                "criteria": criteria,
            }
        },
    }
    url = f"{(api_base or TYPESAFE_DEFAULT_BASE).rstrip('/')}/v1/systemone"
    started = time.perf_counter()
    try:
        response = client.post(
            url,
            json=body,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response.is_error:
            detail = " ".join(response.text.split())[:300]
            raise RuntimeError(f"Decision model returned HTTP {response.status_code}: {detail}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Decision model returned an unexpected response")
        _record_decision_attempt(
            payload,
            requested_model=model_name,
            model_config_id=model_config_id,
            latency_ms=latency_ms,
            status="succeeded",
            error_type=None,
            error_message=None,
        )
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        _record_decision_attempt(
            {},
            requested_model=model_name,
            model_config_id=model_config_id,
            latency_ms=latency_ms,
            status="failed",
            error_type=type(exc).__name__,
            error_message=str(exc)[:500],
        )
        raise
    return _choice_from_payload(payload, criteria)


def english_wikipedia_urls(client: httpx.Client, qids: list[str]) -> dict[str, str]:
    """English Wikipedia page URL for each Wikidata id that has an enwiki sitelink."""
    unique = []
    seen: set[str] = set()
    for qid in qids:
        if _is_qid(qid) and qid not in seen:
            seen.add(qid)
            unique.append(qid)
    found: dict[str, str] = {}
    for start in range(0, len(unique), WIKIDATA_ENTITY_BATCH):
        chunk = unique[start : start + WIKIDATA_ENTITY_BATCH]
        response = client.get(
            WIKIDATA_API_URL,
            params={
                "action": "wbgetentities",
                "ids": "|".join(chunk),
                "props": "sitelinks",
                "sitefilter": "enwiki",
                "format": "json",
            },
        )
        response.raise_for_status()
        payload = response.json()
        entities = payload.get("entities") if isinstance(payload, dict) else None
        if not isinstance(entities, dict):
            continue
        for qid, entity in entities.items():
            url = _english_url(entity)
            if url and isinstance(qid, str):
                found[qid] = url
    return found


def _query_name(organization: dict[str, Any]) -> str:
    raw = organization.get("name")
    if not isinstance(raw, str):
        return ""
    return raw.strip()


def _organization_type(organization: dict[str, Any]) -> str | None:
    raw = organization.get("type")
    if not isinstance(raw, str) or not raw.strip():
        raw = organization.get("organization_type")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _candidates_from_block(block: object) -> list[dict[str, str]]:
    if not isinstance(block, dict):
        return []
    rows = block.get("result")
    if not isinstance(rows, list):
        return []
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        qid = row.get("id")
        if not isinstance(qid, str) or not _is_qid(qid) or qid in seen:
            continue
        seen.add(qid)
        name = row.get("name") if isinstance(row.get("name"), str) else qid
        description = row.get("description") if isinstance(row.get("description"), str) else ""
        candidates.append({"id": qid, "name": name.strip(), "description": description.strip()})
    return candidates


def _choice_criteria(candidates: list[dict[str, str]]) -> dict[str, str]:
    criteria: dict[str, str] = {}
    for candidate in candidates:
        label = candidate["name"] or candidate["id"]
        description = candidate.get("description") or ""
        text = f"{label} — {description}" if description else label
        criteria[candidate["id"]] = text[:240]
    criteria["none"] = _NONE_CRITERION
    return criteria


def _decision_state(
    organization: dict[str, Any],
    candidates: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "organization": {
            "name": _text(organization.get("name")),
            "type": _organization_type(organization),
            "role_in_story": _text(organization.get("role_in_story")),
        },
        "candidates": [
            {
                "id": candidate["id"],
                "name": candidate["name"],
                "description": candidate["description"],
            }
            for candidate in candidates
        ],
    }


def _choice_from_payload(
    payload: dict[str, Any],
    criteria: dict[str, str],
) -> tuple[str | None, float | None]:
    answers = payload.get("answers")
    match = answers.get("match") if isinstance(answers, dict) else None
    if not isinstance(match, dict):
        return None, None
    choice = match.get("choice")
    if not isinstance(choice, str) or choice not in criteria:
        return None, None
    confidence = _as_float(match.get("confidence"))
    if choice == "none":
        return None, confidence
    if not _is_qid(choice):
        return None, confidence
    return choice, confidence


def _english_url(entity: object) -> str | None:
    if not isinstance(entity, dict):
        return None
    sitelinks = entity.get("sitelinks")
    enwiki = sitelinks.get("enwiki") if isinstance(sitelinks, dict) else None
    title = enwiki.get("title") if isinstance(enwiki, dict) else None
    if not isinstance(title, str) or not title.strip():
        return None
    slug = quote(title.strip().replace(" ", "_"), safe="/")
    return f"https://en.wikipedia.org/wiki/{slug}"


def _record_decision_attempt(
    payload: dict[str, Any],
    *,
    requested_model: str,
    model_config_id: str | None,
    latency_ms: int,
    status: str,
    error_type: str | None,
    error_message: str | None,
) -> None:
    reported = payload.get("model")
    if isinstance(reported, str) and reported.strip():
        provider_model_id = reported.strip()
    else:
        provider_model_id = requested_model
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    prompt_tokens = _as_int(usage.get("input_tokens"))
    completion_tokens = _as_int(usage.get("output_tokens"))
    total = None
    if prompt_tokens is not None or completion_tokens is not None:
        total = (prompt_tokens or 0) + (completion_tokens or 0)
    try:
        persist_llm_attempt(
            provider="typesafe",
            provider_model_id=provider_model_id,
            status=status,
            attempt_number=1,
            model_config_id=model_config_id,
            model_config_snapshot_json={
                "provider": "typesafe",
                "provider_model_id": provider_model_id,
            },
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total,
            estimated_cost=None,
            currency="USD",
            cost_estimate_incomplete=True,
            latency_ms=latency_ms,
            provider_request_id=None,
            error_type=error_type,
            error_message=error_message,
            cost_estimate_source=None,
            model_kind=AI_MODEL_KIND_DECISION,
        )
    except Exception:
        logger.warning("Could not record decision model usage", exc_info=True)


def _is_qid(value: str) -> bool:
    return value.startswith("Q") and value[1:].isdigit()


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
