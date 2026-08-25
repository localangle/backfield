"""Tests for evidence-first automatic connection candidates."""

from __future__ import annotations

import json

from backfield_entities.connections.candidate_pairs import (
    build_deterministic_connection_proposals,
    generate_connection_candidates,
    select_linked_entities_with_pair_priority,
)
from backfield_entities.connections.inference import classify_candidate_batches
from backfield_entities.connections.types import LinkedEntitySnapshot


def _person(
    canonical_id: str,
    label: str,
    *,
    affiliation: str | None = None,
    snippets: tuple[str, ...] = (),
) -> LinkedEntitySnapshot:
    return LinkedEntitySnapshot(
        entity_type="person",
        substrate_id=1,
        canonical_id=canonical_id,
        label=label,
        affiliation=affiliation,
        snippets=snippets,
    )


def _organization(
    canonical_id: str,
    label: str,
    *,
    snippets: tuple[str, ...] = (),
) -> LinkedEntitySnapshot:
    return LinkedEntitySnapshot(
        entity_type="organization",
        substrate_id=2,
        canonical_id=canonical_id,
        label=label,
        organization_type="sports_team",
        snippets=snippets,
    )


def test_generates_mount_carmel_pairs_from_article_sentences() -> None:
    people = (
        _person("lynch", "Jordan Lynch", affiliation="Mount Carmel"),
        _person("startz", "Ryder Startz", affiliation="Mount Carmel"),
        _person("samuels", "Nathan Samuels", affiliation="Mount Carmel"),
    )
    organization = _organization(
        "mount-carmel",
        "Mount Carmel High School boys football team",
    )
    article = (
        "Mount Carmel coach Jordan Lynch said the program must improve. "
        "Mount Carmel starting quarterback Ryder Startz was injured. "
        "Nathan Samuels had 19 carries for Mount Carmel."
    )

    result = generate_connection_candidates(
        people=people,
        organizations=(organization,),
        locations=(),
        article_text=article,
        limit=64,
    )

    person_org = [
        candidate
        for candidate in result.candidates
        if candidate.from_entity_type == "person"
        and candidate.to_entity_type == "organization"
    ]
    assert {candidate.from_entity.canonical_id for candidate in person_org} == {
        "lynch",
        "startz",
        "samuels",
    }
    assert all(candidate.evidence.source == "same_sentence" for candidate in person_org)
    assert all(candidate.evidence.snippets for candidate in person_org)


def test_affiliation_is_only_a_lower_trust_candidate_hint() -> None:
    person = _person(
        "cloherty",
        "Brady Cloherty",
        affiliation="Mount Carmel",
        snippets=("Brady Cloherty completed 14 of 30 passes.",),
    )
    organization = _organization(
        "mount-carmel",
        "Mount Carmel High School boys football team",
        snippets=("The Caravan opened its season on Saturday.",),
    )

    result = generate_connection_candidates(
        people=(person,),
        organizations=(organization,),
        locations=(),
        article_text="Brady Cloherty completed 14 of 30 passes. The Caravan lost.",
        limit=64,
    )

    candidate = result.candidates[0]
    assert candidate.evidence.source == "metadata_hint"
    assert candidate.evidence.score < 20
    assert candidate.evidence.hints


def test_linked_occurrence_supports_article_alias_without_label_match() -> None:
    quote = "The Caravan coach Jordan Lynch prepared for Friday's game."
    person = _person("lynch", "Jordan Lynch", snippets=(quote,))
    organization = _organization(
        "mount-carmel",
        "Mount Carmel High School boys football team",
        snippets=(quote,),
    )

    result = generate_connection_candidates(
        people=(person,),
        organizations=(organization,),
        locations=(),
        article_text=quote,
        limit=64,
    )

    candidate = next(
        row
        for row in result.candidates
        if row.from_entity_type == "person"
        and row.to_entity_type == "organization"
    )
    assert candidate.evidence.source == "linked_same_sentence"
    assert candidate.evidence.snippets == (quote,)


def test_sentence_windows_preserve_common_name_abbreviations() -> None:
    quote = "East St. Louis quarterback Reece Shanklin threw two touchdowns."
    result = generate_connection_candidates(
        people=(_person("reece", "Reece Shanklin"),),
        organizations=(
            _organization(
                "east-st-louis",
                "East St. Louis High School football team",
            ),
        ),
        locations=(),
        article_text=quote,
        limit=64,
    )

    candidate = next(
        row
        for row in result.candidates
        if row.from_entity_type == "person"
        and row.to_entity_type == "organization"
    )
    assert candidate.evidence.snippets == (quote,)


def test_rejects_pairs_without_text_or_metadata_evidence() -> None:
    result = generate_connection_candidates(
        people=(_person("jane", "Jane Doe"),),
        organizations=(_organization("acme", "Acme Corporation"),),
        locations=(),
        article_text="A city council meeting occurred.",
        limit=64,
    )

    assert result.candidates == ()
    assert result.stats.rejected_no_evidence == 1


def test_same_type_candidates_are_unordered_and_never_self_pairs() -> None:
    people = (
        _person("a", "Alice Adams"),
        _person("b", "Bob Brown"),
    )
    result = generate_connection_candidates(
        people=people,
        organizations=(),
        locations=(),
        article_text="Alice Adams works with Bob Brown.",
        limit=64,
    )

    pairs = [
        candidate
        for candidate in result.candidates
        if candidate.from_entity_type == candidate.to_entity_type == "person"
    ]
    assert len(pairs) == 1
    assert pairs[0].from_entity.canonical_id != pairs[0].to_entity.canonical_id


def test_candidate_limit_reports_truncation() -> None:
    people = tuple(_person(str(index), f"Person {index}") for index in range(4))
    organization = _organization("team", "Example High School football team")
    article = " ".join(
        f"Person {index} plays for Example High School." for index in range(4)
    )

    result = generate_connection_candidates(
        people=people,
        organizations=(organization,),
        locations=(),
        article_text=article,
        limit=2,
    )

    assert len(result.candidates) == 2
    assert result.stats.truncated > 0


def test_mount_carmel_evidence_supports_coach_and_player_natures() -> None:
    people = (
        _person("lynch", "Jordan Lynch", affiliation="Mount Carmel"),
        _person("startz", "Ryder Startz", affiliation="Mount Carmel"),
        _person("samuels", "Nathan Samuels", affiliation="Mount Carmel"),
    )
    organization = _organization(
        "mount-carmel",
        "Mount Carmel High School boys football team",
    )
    article = (
        "Mount Carmel coach Jordan Lynch said the program must improve. "
        "Mount Carmel starting quarterback Ryder Startz was injured. "
        "Nathan Samuels had 19 carries for Mount Carmel."
    )
    generation = generate_connection_candidates(
        people=people,
        organizations=(organization,),
        locations=(),
        article_text=article,
        limit=64,
    )
    person_org = {
        candidate.from_entity.canonical_id: candidate
        for candidate in generation.candidates
        if candidate.from_entity_type == "person"
        and candidate.to_entity_type == "organization"
    }
    deterministic = build_deterministic_connection_proposals(
        tuple(person_org.values())
    )
    assert {(edge.from_entity_id, edge.nature) for edge in deterministic} == {
        ("lynch", "coaches"),
        ("startz", "plays_for"),
        ("samuels", "plays_for"),
    }

    def call_llm(_prompt: str, **_kwargs: object) -> str:
        return json.dumps(
            {
                "edges": [
                    {
                        "candidate_id": candidate.candidate_id,
                        "from_entity_id": person_id,
                        "to_entity_id": "mount-carmel",
                        "description": (
                            "Jordan Lynch coaches Mount Carmel."
                            if person_id == "lynch"
                            else f"{candidate.from_entity.label} plays for Mount Carmel."
                        ),
                        "nature": "coaches" if person_id == "lynch" else "plays_for",
                        "confidence": 0.98,
                        "quote": candidate.evidence.snippets[0],
                    }
                    for person_id, candidate in person_org.items()
                ]
            }
        )

    inference = classify_candidate_batches(
        candidates=tuple(person_org.values()),
        model="test",
        model_config_id=None,
        call_llm=call_llm,
        max_requests=1,
    )

    assert {
        (edge.from_entity_id, edge.nature)
        for edge in inference.edges
    } == {
        ("lynch", "coaches"),
        ("startz", "plays_for"),
        ("samuels", "plays_for"),
    }


def test_pair_priority_selection_keeps_low_rank_org_with_textual_evidence() -> None:
    filler_people = tuple(
        _person(f"person-{index}", f"Player {index}")
        for index in range(20)
    )
    coach = _person("coach-1", "Alex Coach")
    people = filler_people + (coach,)

    filler_orgs = tuple(
        _organization(f"org-{index}", f"Organization {index}")
        for index in range(26)
    )
    barrington = _organization(
        "barrington",
        "Barrington High School boys football team",
    )
    organizations = filler_orgs + (barrington,)

    article = (
        "Organization 0 opened the season with a win. "
        "Barrington coach Alex Coach said the team must improve execution. "
        "Organization 1 also played on Friday."
    )

    selected_people, selected_orgs, _selected_locations = (
        select_linked_entities_with_pair_priority(
            people=people,
            organizations=organizations,
            locations=(),
            article_text=article,
            limit_per_type=16,
        )
    )

    assert coach in selected_people
    assert barrington in selected_orgs
    assert len(selected_people) == 16
    assert len(selected_orgs) == 16


def test_pair_priority_selection_preserves_occurrence_order_without_evidence() -> None:
    people = tuple(_person(f"person-{index}", f"Person {index}") for index in range(20))
    organizations = tuple(
        _organization(f"org-{index}", f"Organization {index}") for index in range(20)
    )
    article = "Person 0 and Organization 0 were mentioned in separate paragraphs."

    selected_people, selected_orgs, _selected_locations = (
        select_linked_entities_with_pair_priority(
            people=people,
            organizations=organizations,
            locations=(),
            article_text=article,
            limit_per_type=16,
        )
    )

    assert [person.canonical_id for person in selected_people] == [
        f"person-{index}" for index in range(16)
    ]
    assert [org.canonical_id for org in selected_orgs] == [
        f"org-{index}" for index in range(16)
    ]
