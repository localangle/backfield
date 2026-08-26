"""Tests for generalized same-site org→location name matching and edges."""

from __future__ import annotations

from backfield_entities.connections.match_tokens import (
    MATCH_BASIS_ORG_AT_NAMED_PLACE,
    MATCH_BASIS_SITE_NAME_EXACT,
    head_name_tokens,
    org_location_site_names_match,
)
from backfield_entities.connections.same_site_links import (
    infer_same_site_org_location_edges,
    org_type_eligible_for_same_site,
)
from backfield_entities.connections.snippets import collect_pair_snippets_for_entities
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

_CARMEL_ARTICLE = (
    "Nebraska commit Trae Taylor, the consensus No. 1 quarterback nationally in the "
    "2027 cycle, and wide receiver Greg Bess-Henning have transferred out of Carmel, "
    "but the cupboard's not bare."
)

_APOLLO_ARTICLE = (
    "The show at the Apollo Theater drew a sold-out crowd on Friday night in Chicago."
)

_GRANT_PARK_ARTICLE = (
    "Vendors opened early at the Grant Park Farmers Market before crowds filled "
    "Grant Park for the afternoon."
)


def _org(
    *,
    canonical_id: str,
    label: str,
    organization_type: str = "school",
    snippets: tuple[str, ...] = (),
) -> LinkedEntitySnapshot:
    return LinkedEntitySnapshot(
        entity_type="organization",
        substrate_id=1,
        canonical_id=canonical_id,
        label=label,
        organization_type=organization_type,
        snippets=snippets,
    )


def _location(
    *,
    canonical_id: str,
    label: str,
    snippets: tuple[str, ...] = (),
) -> LinkedEntitySnapshot:
    return LinkedEntitySnapshot(
        entity_type="location",
        substrate_id=2,
        canonical_id=canonical_id,
        label=label,
        location_type="place",
        snippets=snippets,
    )


def test_head_name_tokens_from_labels() -> None:
    assert head_name_tokens("Apollo Theater, Chicago, IL") == ("apollo", "theater")
    assert head_name_tokens("Grant Park Farmers Market") == (
        "grant",
        "park",
        "farmers",
        "market",
    )


def test_org_location_site_names_match_examples() -> None:
    assert org_location_site_names_match(
        "Apollo Theater",
        "Apollo Theater, Chicago, IL",
    ) == (True, MATCH_BASIS_SITE_NAME_EXACT)
    assert org_location_site_names_match(
        "Grant Park Farmers Market",
        "Grant Park, Chicago, IL",
    ) == (True, MATCH_BASIS_ORG_AT_NAMED_PLACE)
    assert org_location_site_names_match(
        "Carmel Catholic High School boys football team",
        "Carmel Catholic High School, Mundelein, IL",
    ) == (True, MATCH_BASIS_ORG_AT_NAMED_PLACE)
    assert org_location_site_names_match(
        "Grant Park Summer Festival",
        "Grant Park, Chicago, IL",
    ) == (True, MATCH_BASIS_ORG_AT_NAMED_PLACE)
    assert org_location_site_names_match(
        "Byrne Elementary",
        "Byrne Elementary, Garfield Ridge, Chicago, IL",
    ) == (True, MATCH_BASIS_SITE_NAME_EXACT)


def test_org_location_site_names_rejects_city_only_prefix() -> None:
    assert org_location_site_names_match(
        "Chicago Public Schools",
        "Chicago, IL",
    ) == (False, "")
    assert org_location_site_names_match(
        "Chicago Bears",
        "Chicago, IL",
    ) == (False, "")


def test_org_location_site_names_rejects_divergent_shared_prefix() -> None:
    assert org_location_site_names_match(
        "Northwestern Memorial Hospital",
        "Northwestern University, Evanston, IL",
    ) == (False, "")


def test_sports_team_is_eligible_for_same_site() -> None:
    assert org_type_eligible_for_same_site("sports_team")
    assert not org_type_eligible_for_same_site("school_district")


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


def test_infer_same_site_edge_for_byrne_excludes_school_district() -> None:
    orgs = (
        _org(
            canonical_id="cps",
            label="Chicago Public Schools",
            organization_type="school_district",
        ),
        _org(canonical_id="byrne", label="Byrne Elementary", organization_type="school"),
    )
    loc = _location(
        canonical_id="byrne-loc",
        label="Byrne Elementary, Garfield Ridge, Chicago, IL",
    )
    edges = infer_same_site_org_location_edges(
        organizations=orgs,
        locations=(loc,),
        article_text=_BYRNE_ARTICLE,
    )
    assert len(edges) == 1
    assert edges[0].from_entity_id == "byrne"
    assert edges[0].to_entity_id == "byrne-loc"
    assert edges[0].nature == "located_at"


def test_infer_same_site_edge_for_carmel_team_and_school_place() -> None:
    org = _org(
        canonical_id="team",
        label="Carmel Catholic High School boys football team",
        organization_type="sports_team",
        snippets=(_CARMEL_ARTICLE,),
    )
    loc = _location(
        canonical_id="place",
        label="Carmel Catholic High School, Mundelein, IL",
        snippets=(_CARMEL_ARTICLE,),
    )
    edges = infer_same_site_org_location_edges(
        organizations=(org,),
        locations=(loc,),
        article_text=_CARMEL_ARTICLE,
    )
    assert len(edges) == 1
    edge = edges[0]
    assert edge.from_entity_id == "team"
    assert edge.to_entity_id == "place"
    assert edge.nature == "located_at"
    assert edge.match_basis == MATCH_BASIS_ORG_AT_NAMED_PLACE
    assert "Carmel" in edge.quote


def test_infer_same_site_edge_for_apollo_theater() -> None:
    org = _org(
        canonical_id="apollo-org",
        label="Apollo Theater",
        organization_type="culture_arts",
    )
    loc = _location(
        canonical_id="apollo-place",
        label="Apollo Theater, Chicago, IL",
    )
    edges = infer_same_site_org_location_edges(
        organizations=(org,),
        locations=(loc,),
        article_text=_APOLLO_ARTICLE,
    )
    assert len(edges) == 1
    assert edges[0].nature == "located_at"


def test_infer_same_site_edge_for_grant_park_market() -> None:
    org = _org(
        canonical_id="market",
        label="Grant Park Farmers Market",
        organization_type="local_business",
    )
    loc = _location(
        canonical_id="park",
        label="Grant Park, Chicago, IL",
    )
    edges = infer_same_site_org_location_edges(
        organizations=(org,),
        locations=(loc,),
        article_text=_GRANT_PARK_ARTICLE,
    )
    assert len(edges) == 1
    assert edges[0].match_basis == MATCH_BASIS_ORG_AT_NAMED_PLACE
