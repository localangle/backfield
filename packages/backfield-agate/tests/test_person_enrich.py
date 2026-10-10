"""Person Enrich lookup behavior with mocked Wikidata and Jev calls."""

from __future__ import annotations

import json

import httpx
from agate_nodes.person_enrich.enrich import (
    MISSING_CREDENTIAL_WARNING,
    MISSING_MODEL_WARNING,
    PARTIAL_FAILURE_WARNING,
    enrich_public_figures,
)
from agate_nodes.person_enrich.params import PersonEnrichParams
from agate_nodes.person_enrich.runner import run_person_enrich_with_context
from agate_runtime.context import AgateEnvContext


def _settings(**overrides: object) -> PersonEnrichParams:
    payload: dict[str, object] = {
        "aiModelConfigId": "cfg-1",
        "sources": ["wikidata", "wikipedia"],
        "confidence_cutoff": 0.95,
    }
    payload.update(overrides)
    return PersonEnrichParams.model_validate(payload)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_default_confidence_cutoff_is_point_eight() -> None:
    settings = PersonEnrichParams.model_validate({"place_context": "Chicago"})
    assert settings.confidence_cutoff == 0.8


def test_cutoff_rejects_a_weak_match_and_wikipedia_uses_the_sitelink() -> None:
    seen_models: list[str] = []
    seen_instructions: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "wikidata-reconciliation.wmcloud.org":
            return httpx.Response(
                200,
                json={
                    "0": {
                        "result": [
                            {
                                "id": "Q295584",
                                "name": "Harold Washington",
                                "description": "American politician",
                            }
                        ]
                    },
                    "1": {
                        "result": [
                            {
                                "id": "Q42",
                                "name": "Other Person",
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
            name = body["state"]["person"]["name"]
            if name == "Low Confidence":
                choice, confidence = "Q42", 0.4
            else:
                choice, confidence = "Q295584", 0.99
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
                        "Q295584": {"sitelinks": {"enwiki": {"title": "Harold Washington"}}},
                    }
                },
            )
        return httpx.Response(404)

    people = [
        {
            "name": "Harold Washington",
            "title": "Mayor",
            "affiliation": "Chicago",
            "public_figure": True,
        },
        {"name": "Low Confidence", "public_figure": True},
        {"name": "Private Person", "public_figure": False},
    ]
    with _client(handler) as client:
        enriched, warnings = enrich_public_figures(
            people,
            _settings(),
            litellm_model="typesafe/jev-latest",
            api_key="test-key",
            api_base="https://api.typesafe.ai",
            cached_links=lambda _person: None,
            system_prompt="Chicago editorial rules",
            client=client,
        )
    assert warnings == []
    assert seen_models == ["jev-latest", "jev-latest"]
    assert seen_instructions
    assert all(text.endswith("Chicago editorial rules") for text in seen_instructions)
    assert enriched[0]["wikidata_id"] == "Q295584"
    assert enriched[0]["wikipedia_url"] == "https://en.wikipedia.org/wiki/Harold_Washington"
    assert "wikidata_id" not in enriched[1]
    assert "wikipedia_url" not in enriched[1]
    assert "wikidata_id" not in enriched[2]


def test_cache_hit_skips_outside_calls() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("outside call")

    people = [{"name": "Harold Washington", "public_figure": True, "affiliation": "Chicago"}]
    with _client(handler) as client:
        enriched, warnings = enrich_public_figures(
            people,
            _settings(),
            litellm_model="typesafe/jev-latest",
            api_key="test-key",
            api_base=None,
            cached_links=lambda _person: {
                "wikidata_id": "Q295584",
                "wikipedia_url": "https://en.wikipedia.org/wiki/Harold_Washington",
            },
            client=client,
        )
    assert warnings == []
    assert enriched[0]["wikidata_id"] == "Q295584"
    assert enriched[0]["wikipedia_url"] == "https://en.wikipedia.org/wiki/Harold_Washington"


def test_missing_credential_leaves_people_unchanged() -> None:
    people = [{"name": "Harold Washington", "public_figure": True}]
    enriched, warnings = enrich_public_figures(
        people,
        _settings(),
        litellm_model="typesafe/jev-latest",
        api_key=None,
        api_base=None,
        cached_links=lambda _person: None,
    )
    assert warnings == [MISSING_CREDENTIAL_WARNING]
    assert enriched == people
    assert "wikidata_id" not in enriched[0]


def test_missing_model_leaves_people_unchanged() -> None:
    people = [{"name": "Harold Washington", "public_figure": True}]
    _enriched, warnings = enrich_public_figures(
        people,
        _settings(aiModelConfigId=None),
        litellm_model="typesafe/jev-latest",
        api_key="test-key",
        api_base=None,
        cached_links=lambda _person: None,
    )
    assert warnings == [MISSING_MODEL_WARNING]


def test_reconciliation_failure_warns_and_continues() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    people = [{"name": "Harold Washington", "public_figure": True}]
    with _client(handler) as client:
        enriched, warnings = enrich_public_figures(
            people,
            _settings(),
            litellm_model="typesafe/jev-latest",
            api_key="test-key",
            api_base="https://api.typesafe.ai",
            cached_links=lambda _person: None,
            client=client,
        )
    assert warnings == [PARTIAL_FAILURE_WARNING]
    assert "wikidata_id" not in enriched[0]


def test_runner_without_a_project_records_a_warning() -> None:
    output = run_person_enrich_with_context(
        {"aiModelConfigId": "cfg-1", "sources": ["wikidata"]},
        {"node-3": {"people": [{"name": "Harold Washington", "public_figure": True}]}},
        AgateEnvContext(project_id=None),
    )
    assert output["warnings"] == [MISSING_CREDENTIAL_WARNING]
    assert output["people"][0]["name"] == "Harold Washington"
    assert "wikidata_id" not in output["people"][0]
