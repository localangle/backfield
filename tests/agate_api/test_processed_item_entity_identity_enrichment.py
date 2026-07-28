"""Regression tests for article-scoped processed-item entity identity."""

from __future__ import annotations

from api.processed_item.entities.location.review_enrichment import (
    enrich_merged_locations_for_review,
)
from api.processed_item.entities.organization.review_enrichment import (
    enrich_merged_organizations_for_review,
)
from api.processed_item.entities.person.review_enrichment import enrich_merged_people_for_review
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstratePerson,
    SubstratePersonMention,
)
from backfield_entities.canonical.link import CANONICAL_LINK_LINKED
from backfield_entities.entities.organization.types import organization_identity_fingerprint
from backfield_entities.entities.person.types import person_identity_fingerprint
from sqlmodel import Session, SQLModel, create_engine


def _context(session: Session, *, suffix: str) -> tuple[int, int, int]:
    organization = BackfieldOrganization(name=f"Org {suffix}", slug=f"org-{suffix}")
    session.add(organization)
    session.commit()
    session.refresh(organization)
    stylebook = Stylebook(
        organization_id=int(organization.id),
        name=f"Stylebook {suffix}",
        slug=f"stylebook-{suffix}",
        is_default=True,
    )
    project = BackfieldProject(
        organization_id=int(organization.id),
        name=f"Project {suffix}",
        slug=f"project-{suffix}",
    )
    session.add(stylebook)
    session.add(project)
    session.commit()
    session.refresh(stylebook)
    session.refresh(project)
    article = SubstrateArticle(
        project_id=int(project.id),
        headline="Identity regression",
        text="Body",
    )
    session.add(article)
    session.commit()
    session.refresh(article)
    return int(stylebook.id), int(project.id), int(article.id)


def test_organization_enrichment_ignores_crossed_positional_anchors() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, article_id = _context(session, suffix="org-cross")
        specs = [
            ("Colorado Avalanche", "stylebook_output:5"),
            ("Buffalo Sabres", "stylebook_output:1"),
            ("National Hockey League", "stylebook_output:2"),
        ]
        organizations: dict[str, SubstrateOrganization] = {}
        for name, stale_anchor in specs:
            organization_type = (
                "sports_league" if name == "National Hockey League" else "sports_team"
            )
            canonical = StylebookOrganizationCanonical(
                stylebook_id=stylebook_id,
                label=name,
                slug=name.lower().replace(" ", "-"),
                organization_type=organization_type,
            )
            session.add(canonical)
            session.flush()
            organization = SubstrateOrganization(
                project_id=project_id,
                name=name,
                normalized_name=name.lower(),
                organization_type=organization_type,
                identity_fingerprint=organization_identity_fingerprint(
                    normalized_name=name.lower(),
                    organization_type=organization_type,
                ),
                stylebook_organization_canonical_id=str(canonical.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
                source_details_json={
                    "run_id": "run-cross",
                    "raw_entry_id": stale_anchor,
                },
            )
            session.add(organization)
            session.flush()
            organizations[name] = organization
            session.add(
                SubstrateOrganizationMention(
                    article_id=article_id,
                    organization_id=int(organization.id),
                )
            )
        session.commit()

        current_rows = [
            ("stylebook_output:1", "Colorado Avalanche", "sports_team"),
            ("stylebook_output:2", "Buffalo Sabres", "sports_team"),
            ("stylebook_output:5", "National Hockey League", "sports_league"),
        ]
        merged = [
            {
                "anchor": anchor,
                "organization": {"id": anchor, "name": name, "type": organization_type},
            }
            for anchor, name, organization_type in current_rows
        ]
        out = enrich_merged_organizations_for_review(
            session,
            project_id=project_id,
            run_id="run-cross",
            article_id=article_id,
            merged_organizations=merged,
        )

        assert len(out) == 3
        for row, (_anchor, expected_name, _type) in zip(out, current_rows, strict=True):
            expected = organizations[expected_name]
            assert row["persisted_organization_id"] == int(expected.id)
            assert row["stylebook_link"]["label"] == expected_name


def test_appended_organization_includes_canonical_metadata() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, article_id = _context(session, suffix="org-append")
        canonical = StylebookOrganizationCanonical(
            stylebook_id=stylebook_id,
            label="League Office",
            slug="league-office",
            organization_type="sports_league",
        )
        session.add(canonical)
        session.flush()
        organization = SubstrateOrganization(
            project_id=project_id,
            name="League Office",
            normalized_name="league office",
            organization_type="sports_league",
            identity_fingerprint=organization_identity_fingerprint(
                normalized_name="league office",
                organization_type="sports_league",
            ),
            stylebook_organization_canonical_id=str(canonical.id),
            canonical_link_status=CANONICAL_LINK_LINKED,
        )
        session.add(organization)
        session.flush()
        session.add(
            SubstrateOrganizationMention(
                article_id=article_id,
                organization_id=int(organization.id),
                source_details_json={
                    "run_id": "run-append",
                    "raw_entry_id": "user_organization:league-office",
                },
            )
        )
        session.commit()

        out = enrich_merged_organizations_for_review(
            session,
            project_id=project_id,
            run_id="run-append",
            article_id=article_id,
            merged_organizations=[],
        )

        assert len(out) == 1
        assert out[0]["anchor"] == "user_organization:league-office"
        assert out[0]["stylebook_organization_canonical_id"] == str(canonical.id)
        assert out[0]["stylebook_link"]["label"] == "League Office"


def test_person_enrichment_ignores_crossed_positional_anchors() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, article_id = _context(session, suffix="person-cross")
        specs = [
            ("Cale Makar", "stylebook_output:2"),
            ("Rasmus Dahlin", "stylebook_output:1"),
        ]
        people: dict[str, SubstratePerson] = {}
        for name, stale_anchor in specs:
            canonical = StylebookPersonCanonical(
                stylebook_id=stylebook_id,
                label=name,
                slug=name.lower().replace(" ", "-"),
            )
            session.add(canonical)
            session.flush()
            person = SubstratePerson(
                project_id=project_id,
                name=name,
                normalized_name=name.lower(),
                identity_fingerprint=person_identity_fingerprint(
                    normalized_name=name.lower(),
                    affiliation=None,
                ),
                stylebook_person_canonical_id=str(canonical.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
                source_details_json={
                    "run_id": "run-person-cross",
                    "raw_entry_id": stale_anchor,
                },
            )
            session.add(person)
            session.flush()
            people[name] = person
            session.add(
                SubstratePersonMention(
                    article_id=article_id,
                    person_id=int(person.id),
                )
            )
        session.commit()

        current_rows = [
            ("stylebook_output:1", "Cale Makar"),
            ("stylebook_output:2", "Rasmus Dahlin"),
        ]
        out = enrich_merged_people_for_review(
            session,
            project_id=project_id,
            run_id="run-person-cross",
            article_id=article_id,
            merged_people=[
                {"anchor": anchor, "person": {"id": anchor, "name": name}}
                for anchor, name in current_rows
            ],
        )

        assert len(out) == 2
        for row, (_anchor, expected_name) in zip(out, current_rows, strict=True):
            assert row["persisted_person_id"] == int(people[expected_name].id)
            assert row["stylebook_link"]["label"] == expected_name


def test_location_enrichment_uses_unique_display_identity_before_legacy_position() -> None:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        stylebook_id, project_id, article_id = _context(session, suffix="location-cross")
        specs = [
            ("Chicago, IL", "stylebook_output:1"),
            ("Buffalo, NY", "stylebook_output:0"),
        ]
        locations: dict[str, SubstrateLocation] = {}
        for name, stale_anchor in specs:
            canonical = StylebookLocationCanonical(
                stylebook_id=stylebook_id,
                label=name,
                slug=name.lower().replace(",", "").replace(" ", "-"),
            )
            session.add(canonical)
            session.flush()
            location = SubstrateLocation(
                project_id=project_id,
                name=name,
                normalized_name=name.lower(),
                stylebook_location_canonical_id=str(canonical.id),
                canonical_link_status=CANONICAL_LINK_LINKED,
                source_details_json={
                    "run_id": "run-location-cross",
                    "raw_entry_id": stale_anchor,
                },
            )
            session.add(location)
            session.flush()
            locations[name] = location
            session.add(
                SubstrateLocationMention(
                    article_id=article_id,
                    location_id=int(location.id),
                )
            )
        session.commit()

        current_rows = [
            ("stylebook_output:0", "Chicago, IL"),
            ("stylebook_output:1", "Buffalo, NY"),
        ]
        out = enrich_merged_locations_for_review(
            session,
            project_id=project_id,
            run_id="run-location-cross",
            article_id=article_id,
            merged_locations=[
                {
                    "anchor": anchor,
                    "location": {"id": anchor, "location": {"full": name}},
                }
                for anchor, name in current_rows
            ],
        )

        assert len(out) == 2
        for row, (_anchor, expected_name) in zip(out, current_rows, strict=True):
            assert row["persisted_location_id"] == int(locations[expected_name].id)
            assert row["stylebook_link"]["label"] == expected_name
