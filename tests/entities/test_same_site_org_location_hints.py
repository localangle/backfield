"""Tests for same-site org→location hint discovery and inference."""

from __future__ import annotations

import json

from backfield_entities.connections.inference import classify_connection_family
from backfield_entities.connections.same_site_hints import (
    discover_same_site_org_location_hints,
    head_names_match,
)
from backfield_entities.connections.snippets import (
    collect_pair_snippets,
    collect_pair_snippets_for_entities,
)
from backfield_entities.connections.types import LinkedEntitySnapshot

_BYRNE_ARTICLE = (
    "After a car crash with a drunken driver left her paralyzed, Byrne Elementary "
    "clerk Judy Mahoney overcame barriers to remain employed. Now, Chicago Public "
    "Schools may cut the position she fought to keep.\n\n"
    "Mahoney, 54, faces termination June 30 — the official end of the school year — "
    "because CPS plans to eliminate the school clerk position at Byrne Elementary "
    "in Garfield Ridge.\n\n"
    "She has worked for CPS for 23 years, the previous eight years at Byrne Elementary."
)


def _org(
    *,
    canonical_id: str,
    label: str,
    organization_type: str = "school",
) -> LinkedEntitySnapshot:
    return LinkedEntitySnapshot(
        entity_type="organization",
        substrate_id=1,
        canonical_id=canonical_id,
        label=label,
        organization_type=organization_type,
    )


def _location(
    *,
    canonical_id: str,
    label: str,
) -> LinkedEntitySnapshot:
    return LinkedEntitySnapshot(
        entity_type="location",
        substrate_id=2,
        canonical_id=canonical_id,
        label=label,
        location_type="place",
    )


def test_head_names_match_for_byrne_pair() -> None:
    byrne_place = "Byrne Elementary, Garfield Ridge, Chicago, IL"
    assert head_names_match("Byrne Elementary", byrne_place)
    assert not head_names_match("Chicago Public Schools", byrne_place)


def test_collect_pair_snippets_finds_byrne_org_and_place() -> None:
    snippets = collect_pair_snippets_for_entities(
        left=_org(canonical_id="org-b", label="Byrne Elementary"),
        right=_location(
            canonical_id="loc-b",
            label="Byrne Elementary, Garfield Ridge, Chicago, IL",
        ),
        article_text=_BYRNE_ARTICLE,
    )
    assert snippets
    assert any("Garfield Ridge" in snippet for snippet in snippets)
    assert any("Byrne Elementary" in snippet for snippet in snippets)


def test_discover_same_site_hints_for_byrne_excludes_school_district() -> None:
    orgs = (
        _org(
            canonical_id="cps",
            label="Chicago Public Schools",
            organization_type="school_district",
        ),
        _org(canonical_id="byrne", label="Byrne Elementary", organization_type="school"),
    )
    locs = (
        _location(
            canonical_id="byrne-loc",
            label="Byrne Elementary, Garfield Ridge, Chicago, IL",
        ),
    )
    hints = discover_same_site_org_location_hints(
        organizations=orgs,
        locations=locs,
        article_text=_BYRNE_ARTICLE,
    )
    assert len(hints) == 1
    assert hints[0].org.canonical_id == "byrne"
    assert hints[0].location.canonical_id == "byrne-loc"
    assert hints[0].match_basis == "head_name_match"
    assert hints[0].suggested_snippets


def test_classify_connection_family_uses_pair_fallback_when_family_llm_skips_hint() -> None:
    byrne_org = _org(canonical_id="byrne", label="Byrne Elementary")
    cps = _org(
        canonical_id="cps",
        label="Chicago Public Schools",
        organization_type="school_district",
    )
    byrne_loc = _location(
        canonical_id="byrne-loc",
        label="Byrne Elementary, Garfield Ridge, Chicago, IL",
    )
    hints = discover_same_site_org_location_hints(
        organizations=(byrne_org, cps),
        locations=(byrne_loc,),
        article_text=_BYRNE_ARTICLE,
    )
    assert len(hints) == 1

    family_calls: list[str] = []
    pair_calls: list[str] = []

    def _fake_family_llm(prompt: str, **_kwargs: object) -> str:
        family_calls.append(prompt)
        return json.dumps({"edges": []})

    def _fake_pair_llm(prompt: str, **_kwargs: object) -> str:
        pair_calls.append(prompt)
        return json.dumps(
            {
                "link": True,
                "nature": "located_at",
                "confidence": 0.95,
                "quote": (
                    "CPS plans to eliminate the school clerk position at Byrne Elementary "
                    "in Garfield Ridge."
                ),
                "reason": "Article places school clerk activity at Byrne Elementary.",
            }
        )

    result = classify_connection_family(
        from_entity_type="organization",
        to_entity_type="location",
        from_entities=(byrne_org, cps),
        to_entities=(byrne_loc,),
        article_text=_BYRNE_ARTICLE,
        model="gpt-test",
        model_config_id=None,
        call_llm=lambda prompt, **kwargs: (
            _fake_pair_llm(prompt, **kwargs)
            if "auto_connections_same_site_pair_v1" in prompt
            else _fake_family_llm(prompt, **kwargs)
        ),
        same_site_hints=hints,
    )

    assert family_calls
    assert "Candidate same-site pairs" in family_calls[0]
    assert pair_calls
    assert len(result.edges) == 1
    edge = result.edges[0]
    assert edge.from_entity_id == "byrne"
    assert edge.to_entity_id == "byrne-loc"
    assert edge.nature == "located_at"
    assert edge.match_basis == "head_name_match"

    snippets = collect_pair_snippets(
        from_entities=(byrne_org, cps),
        to_entities=(byrne_loc,),
        article_text=_BYRNE_ARTICLE,
        extra_snippets=hints[0].suggested_snippets,
    )
    assert snippets
