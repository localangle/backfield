"""Organization Enrich lookup behavior with mocked Wikidata and Jev calls."""

from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx
from agate_nodes.organization_enrich.enrich import (
    MISSING_CREDENTIAL_WARNING,
    MISSING_MODEL_WARNING,
    PARTIAL_FAILURE_WARNING,
    enrich_organizations,
)
from agate_nodes.organization_enrich.params import OrganizationEnrichParams
from agate_nodes.organization_enrich.runner import run_organization_enrich_with_context
from agate_runtime.context import AgateEnvContext


def _settings(**overrides: object) -> OrganizationEnrichParams:
    payload: dict[str, object] = {
        "aiModelConfigId": "cfg-1",
        "sources": ["wikidata", "wikipedia"],
        "confidence_cutoff": 0.8,
    }
    payload.update(overrides)
    return OrganizationEnrichParams.model_validate(payload)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_default_confidence_cutoff_is_point_eight() -> None:
    settings = OrganizationEnrichParams.model_validate({})
    assert settings.confidence_cutoff == 0.8


def test_cutoff_rejects_a_weak_match_and_wikipedia_uses_the_sitelink() -> None:
    seen_models: list[str] = []
    seen_instructions: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "wikidata-reconciliation.wmcloud.org":
            encoded = parse_qs(request.content.decode())
            queries = json.loads(encoded["queries"][0])
            assert queries["0"]["type"] == "Q43229"
            assert queries["0"]["type_strict"] == "should"
            return httpx.Response(
                200,
                json={
                    "0": {
                        "result": [
                            {
                                "id": "Q205041",
                                "name": "Chicago Bears",
                                "description": "NFL team",
                            }
                        ]
                    },
                    "1": {
                        "result": [
                            {
                                "id": "Q42",
                                "name": "Other Org",
                                "description": "someone else",
                            }
                        ]
                    },
                },
            )
        if request.url.path.endswith("/v1/systemone"):
            body = json.loads(request.content.decode())
            seen_models.append(body["model"])
            seen_instructions.append(body["questions"]["match"]["instructions"])
            assert "context" not in body["state"]
            assert isinstance(body["questions"], dict)
            assert body["questions"]["match"]["type"] == "choice"
            name = body["state"]["organization"]["name"]
            if name == "Low Confidence":
                choice, confidence = "Q42", 0.4
            else:
                choice, confidence = "Q205041", 0.99
            return httpx.Response(
                200,
                json={
                    "model": "jev-1.13.0",
                    "answers": {"match": {"choice": choice, "confidence": confidence}},
                    "usage": {"input_tokens": 12, "output_tokens": 3},
                },
            )
        if request.url.host == "www.wikidata.org":
            return httpx.Response(
                200,
                json={
                    "entities": {
                        "Q205041": {"sitelinks": {"enwiki": {"title": "Chicago Bears"}}},
                    }
                },
            )
        return httpx.Response(404)

    organizations = [
        {"name": "Chicago Bears", "type": "sports_team", "role_in_story": "Home team"},
        {"name": "Low Confidence", "type": "company"},
        "not-an-organization",
    ]
    with _client(handler) as client:
        enriched, warnings = enrich_organizations(
            organizations,
            _settings(),
            litellm_model="typesafe/jev-latest",
            api_key="test-key",
            api_base="https://api.typesafe.ai",
            cached_links=lambda _organization: None,
            system_prompt="Chicago editorial rules",
            client=client,
        )
    assert warnings == []
    assert seen_models == ["jev-latest", "jev-latest"]
    assert seen_instructions
    assert all(text.endswith("Chicago editorial rules") for text in seen_instructions)
    assert enriched[0]["wikidata_id"] == "Q205041"
    assert enriched[0]["wikipedia_url"] == "https://en.wikipedia.org/wiki/Chicago_Bears"
    assert "wikidata_id" not in enriched[1]
    assert enriched[2] == "not-an-organization"


def test_cache_hit_skips_outside_calls() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("outside call")

    organizations = [{"name": "Chicago Bears", "type": "sports_team"}]
    with _client(handler) as client:
        enriched, warnings = enrich_organizations(
            organizations,
            _settings(),
            litellm_model="typesafe/jev-latest",
            api_key="test-key",
            api_base=None,
            cached_links=lambda _organization: {
                "wikidata_id": "Q205041",
                "wikipedia_url": "https://en.wikipedia.org/wiki/Chicago_Bears",
            },
            client=client,
        )
    assert warnings == []
    assert enriched[0]["wikidata_id"] == "Q205041"
    assert enriched[0]["wikipedia_url"] == "https://en.wikipedia.org/wiki/Chicago_Bears"


def test_missing_credential_leaves_organizations_unchanged() -> None:
    organizations = [{"name": "Chicago Bears", "type": "sports_team"}]
    enriched, warnings = enrich_organizations(
        organizations,
        _settings(),
        litellm_model="typesafe/jev-latest",
        api_key=None,
        api_base=None,
        cached_links=lambda _organization: None,
    )
    assert warnings == [MISSING_CREDENTIAL_WARNING]
    assert enriched == organizations
    assert "wikidata_id" not in enriched[0]


def test_missing_model_leaves_organizations_unchanged() -> None:
    organizations = [{"name": "Chicago Bears", "type": "sports_team"}]
    _enriched, warnings = enrich_organizations(
        organizations,
        _settings(aiModelConfigId=None),
        litellm_model="typesafe/jev-latest",
        api_key="test-key",
        api_base=None,
        cached_links=lambda _organization: None,
    )
    assert warnings == [MISSING_MODEL_WARNING]


def test_reconciliation_failure_warns_and_continues() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    organizations = [{"name": "Chicago Bears", "type": "sports_team"}]
    with _client(handler) as client:
        enriched, warnings = enrich_organizations(
            organizations,
            _settings(),
            litellm_model="typesafe/jev-latest",
            api_key="test-key",
            api_base="https://api.typesafe.ai",
            cached_links=lambda _organization: None,
            client=client,
        )
    assert warnings == [PARTIAL_FAILURE_WARNING]
    assert "wikidata_id" not in enriched[0]


def test_runner_without_a_project_records_a_warning() -> None:
    output = run_organization_enrich_with_context(
        {"aiModelConfigId": "cfg-1", "sources": ["wikidata"]},
        {"node-3": {"organizations": [{"name": "Chicago Bears", "type": "sports_team"}]}},
        AgateEnvContext(project_id=None),
    )
    assert output["warnings"] == [MISSING_CREDENTIAL_WARNING]
    assert output["organizations"][0]["name"] == "Chicago Bears"
    assert "wikidata_id" not in output["organizations"][0]
