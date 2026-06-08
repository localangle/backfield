"""Tests for affiliation-based person→organization auto-connections."""

from __future__ import annotations

from backfield_entities.connections.affiliation_links import (
    infer_affiliation_person_organization_edges,
)
from backfield_entities.connections.match_tokens import (
    person_affiliation_matches_organization_label,
)
from backfield_entities.connections.snippets import collect_pair_snippets
from backfield_entities.connections.types import LinkedEntitySnapshot


def _person(
    *,
    canonical_id: str = "person-1",
    label: str = "Kyle Schwarber",
    affiliation: str = "Philadelphia Phillies",
    person_type: str = "athlete",
    snippets: tuple[str, ...] = (),
) -> LinkedEntitySnapshot:
    return LinkedEntitySnapshot(
        entity_type="person",
        substrate_id=1,
        canonical_id=canonical_id,
        label=label,
        affiliation=affiliation,
        person_type=person_type,
        snippets=snippets,
    )


def _org(
    *,
    canonical_id: str = "org-1",
    label: str = "Philadelphia Phillies",
    organization_type: str = "sports_team",
) -> LinkedEntitySnapshot:
    return LinkedEntitySnapshot(
        entity_type="organization",
        substrate_id=2,
        canonical_id=canonical_id,
        label=label,
        organization_type=organization_type,
    )


def test_team_nickname_affiliation_matches_full_organization_label() -> None:
    assert person_affiliation_matches_organization_label("Phillies", "Philadelphia Phillies")
    assert person_affiliation_matches_organization_label(
        "Philadelphia Phillies",
        "Philadelphia Phillies",
    )
    assert not person_affiliation_matches_organization_label("Chicago", "Chicago Cubs")


def test_infer_works_for_edge_when_affiliation_matches_but_prose_uses_short_nickname() -> None:
    """Affiliation names the org; quote cites the person without re-matching team nicknames."""
    article_text = (
        "Hawks general manager Kyle Davidson was resourceful to recoup "
        "his third-round-pick investment in this tricky situation."
    )
    person = _person(
        canonical_id="davidson",
        label="Kyle Davidson",
        affiliation="Chicago Blackhawks",
        person_type="sports_executive",
        snippets=(article_text,),
    )
    org = _org(
        canonical_id="blackhawks",
        label="Chicago Blackhawks",
        organization_type="sports_team",
    )
    edges = infer_affiliation_person_organization_edges(
        people=(person,),
        organizations=(org,),
        article_text=article_text,
    )
    assert len(edges) == 1
    assert edges[0].nature == "works_for"
    assert edges[0].from_entity_id == "davidson"
    assert edges[0].to_entity_id == "blackhawks"
    assert "Kyle Davidson" in edges[0].quote


def test_infer_member_of_edge_for_athlete_team_affiliation() -> None:
    article_text = (
        "His 20 home runs trailed only Phillies masher Kyle Schwarber's 22 in the majors."
    )
    person = _person(
        snippets=(
            "His 20 home runs trailed only Phillies masher Kyle Schwarber's 22 in the majors.",
        )
    )
    org = _org()
    edges = infer_affiliation_person_organization_edges(
        people=(person,),
        organizations=(org,),
        article_text=article_text,
    )
    assert len(edges) == 1
    assert edges[0].nature == "member_of"
    assert edges[0].from_entity_id == "person-1"
    assert edges[0].to_entity_id == "org-1"
    assert "Kyle Schwarber" in edges[0].quote


def test_collect_pair_snippets_matches_team_nickname_not_full_label() -> None:
    article_text = (
        "His 20 home runs trailed only Phillies masher Kyle Schwarber's 22 in the majors."
    )
    person = _person(affiliation="Philadelphia Phillies")
    org = _org(label="Philadelphia Phillies")
    snippets = collect_pair_snippets(
        from_entities=(person,),
        to_entities=(org,),
        article_text=article_text,
    )
    assert snippets
    assert "Phillies" in snippets[0]
    assert "Kyle Schwarber" in snippets[0]
