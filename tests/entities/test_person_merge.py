from __future__ import annotations

from uuid import uuid4

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookConnection,
    StylebookOrganizationCanonical,
    StylebookPersonAlias,
    StylebookPersonCanonical,
    StylebookPersonMeta,
    SubstratePerson,
)
from backfield_entities.entities.person.merge import merge_person_canonical_into
from sqlmodel import Session, SQLModel, create_engine, select

from tests.project_helpers import project_ownership_fields


def _seed(session: Session) -> tuple[int, int, int]:
    organization = BackfieldOrganization(name="Org", slug=f"org-person-merge-{uuid4().hex}")
    session.add(organization)
    session.commit()
    organization_id = int(organization.id)  # type: ignore[arg-type]
    stylebook = Stylebook(
        organization_id=organization_id,
        slug="default",
        name="Default",
        is_default=True,
    )
    session.add(stylebook)
    session.commit()
    session.refresh(stylebook)
    project = BackfieldProject(
        **project_ownership_fields(
            session,
            organization_id,
            stylebook_id=int(stylebook.id),  # type: ignore[arg-type]
        ),
        name="Demo",
        slug=f"demo-person-merge-{uuid4().hex}",
        organization_id=organization_id,
        stylebook_id=int(stylebook.id),  # type: ignore[arg-type]
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return organization_id, int(stylebook.id), int(project.id)  # type: ignore[arg-type]


def _canonical(
    session: Session,
    *,
    stylebook_id: int,
    label: str,
    person_type: str | None,
) -> StylebookPersonCanonical:
    row = StylebookPersonCanonical(
        stylebook_id=stylebook_id,
        label=label,
        slug=f"{label.lower().replace(' ', '-')}-{uuid4().hex[:6]}",
        person_type=person_type,
    )
    session.add(row)
    session.flush()
    return row


def test_person_merge_preserves_aliases_metadata_fields_primary_and_connections() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        organization_id, stylebook_id, project_id = _seed(session)
        source = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Jane Doe",
            person_type="elected_official",
        )
        source.title = "Alderperson"
        source.affiliation = "Chicago City Council"
        source.public_figure = True
        source.sort_key = "doe jane"
        target = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="J. Doe",
            person_type="crime_justice_subject",
        )
        substrate = SubstratePerson(
            project_id=project_id,
            name="Jane Doe",
            normalized_name="jane doe",
            stylebook_person_canonical_id=str(source.id),
            canonical_link_status="linked",
        )
        organization = StylebookOrganizationCanonical(
            stylebook_id=stylebook_id,
            label="Chicago City Council",
            slug=f"chicago-city-council-{uuid4().hex[:6]}",
        )
        session.add_all([substrate, organization])
        session.flush()
        source.primary_substrate_person_id = int(substrate.id)  # type: ignore[arg-type]
        session.add(source)
        session.add_all(
            [
                StylebookPersonAlias(
                    person_canonical_id=str(source.id),
                    alias_text="Jane A. Doe",
                    normalized_alias="jane a doe",
                    provenance="substrate_ingest",
                    suppressed=False,
                ),
                StylebookPersonAlias(
                    person_canonical_id=str(source.id),
                    alias_text="Jane Former",
                    normalized_alias="jane former",
                    provenance="stylebook_ui_manual",
                    suppressed=True,
                ),
                StylebookPersonAlias(
                    person_canonical_id=str(source.id),
                    alias_text="Jane Doe",
                    normalized_alias="jane doe",
                    provenance="stylebook_ui_manual",
                    suppressed=True,
                ),
                StylebookPersonMeta(
                    project_id=project_id,
                    stylebook_person_canonical_id=str(source.id),
                    meta_type="wikidata",
                    value_type="text",
                    value_text="Q123",
                    edited=True,
                ),
                StylebookPersonMeta(
                    project_id=project_id,
                    stylebook_person_canonical_id=str(target.id),
                    meta_type="wikidata",
                    value_type="text",
                    value_text="Q123",
                    added=True,
                ),
                StylebookConnection(
                    project_id=project_id,
                    stylebook_id=stylebook_id,
                    from_entity_type="person",
                    from_entity_id=str(source.id),
                    to_entity_type="organization",
                    to_entity_id=str(organization.id),
                    nature="works_for",
                ),
            ]
        )
        session.commit()

        result = merge_person_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
            provenance="stylebook_cleanup_test",
        )
        session.commit()

        assert result.person_type == "elected_official"
        assert result.transferred_alias_count >= 2
        assert session.get(StylebookPersonCanonical, str(source.id)) is None
        merged = session.get(StylebookPersonCanonical, str(target.id))
        assert merged is not None
        assert merged.title == "Alderperson"
        assert merged.affiliation == "Chicago City Council"
        assert merged.public_figure is True
        assert merged.person_type == "elected_official"
        assert merged.sort_key == "doe jane"
        assert merged.primary_substrate_person_id == substrate.id
        session.refresh(substrate)
        assert substrate.stylebook_person_canonical_id == str(target.id)

        aliases = session.exec(
            select(StylebookPersonAlias).where(
                StylebookPersonAlias.person_canonical_id == str(target.id)
            )
        ).all()
        aliases_by_norm = {row.normalized_alias: row for row in aliases}
        assert aliases_by_norm["jane a doe"].provenance == "stylebook_cleanup_test"
        assert aliases_by_norm["jane former"].suppressed is True
        assert aliases_by_norm["jane doe"].suppressed is True

        meta = session.exec(
            select(StylebookPersonMeta).where(
                StylebookPersonMeta.stylebook_person_canonical_id == str(target.id),
                StylebookPersonMeta.meta_type == "wikidata",
            )
        ).one()
        assert meta.value_text == "Q123"
        assert meta.added is True
        assert meta.edited is True

        connection = session.exec(select(StylebookConnection)).one()
        assert connection.from_entity_id == str(target.id)
        assert connection.to_entity_id == str(organization.id)


def test_person_merge_refuses_conflicting_metadata_before_relinking() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        organization_id, stylebook_id, project_id = _seed(session)
        source = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Jane Source",
            person_type="community_member",
        )
        target = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Jane Target",
            person_type="community_member",
        )
        substrate = SubstratePerson(
            project_id=project_id,
            name="Jane Source",
            normalized_name="jane source",
            stylebook_person_canonical_id=str(source.id),
            canonical_link_status="linked",
        )
        session.add(substrate)
        session.add_all(
            [
                StylebookPersonMeta(
                    project_id=project_id,
                    stylebook_person_canonical_id=str(source.id),
                    meta_type="wikidata",
                    value_type="text",
                    value_text="Q1",
                ),
                StylebookPersonMeta(
                    project_id=project_id,
                    stylebook_person_canonical_id=str(target.id),
                    meta_type="wikidata",
                    value_type="text",
                    value_text="Q2",
                ),
            ]
        )
        session.commit()

        with pytest.raises(ValueError, match="metadata conflict"):
            merge_person_canonical_into(
                session,
                stylebook_id=stylebook_id,
                organization_id=organization_id,
                source_canonical_id=str(source.id),
                target_canonical_id=str(target.id),
            )
        session.rollback()

        session.refresh(substrate)
        assert substrate.stylebook_person_canonical_id == str(source.id)
        assert session.get(StylebookPersonCanonical, str(source.id)) is not None


def test_person_merge_allows_explicit_type_override() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        organization_id, stylebook_id, _project_id = _seed(session)
        source = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Jane Source",
            person_type="elected_official",
        )
        target = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Jane Target",
            person_type="government_official",
        )
        session.commit()

        result = merge_person_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
            resolved_person_type="education_research_expert",
        )
        session.commit()

        assert result.person_type == "education_research_expert"
        merged = session.get(StylebookPersonCanonical, str(target.id))
        assert merged is not None
        assert merged.person_type == "education_research_expert"
