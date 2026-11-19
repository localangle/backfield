from __future__ import annotations

from uuid import uuid4

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    StylebookOrganizationMeta,
    SubstrateOrganization,
)
from backfield_entities.entities.organization import merge as organization_merge
from backfield_entities.entities.organization.merge import merge_organization_canonical_into
from sqlmodel import Session, SQLModel, create_engine, select

from tests.project_helpers import project_ownership_fields


def _seed(session: Session) -> tuple[int, int, int]:
    organization = BackfieldOrganization(name="Org", slug=f"org-merge-{uuid4().hex}")
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
        slug=f"demo-org-merge-{uuid4().hex}",
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
    organization_type: str | None,
) -> StylebookOrganizationCanonical:
    row = StylebookOrganizationCanonical(
        stylebook_id=stylebook_id,
        label=label,
        slug=f"{label.lower().replace(' ', '-')}-{uuid4().hex[:6]}",
        organization_type=organization_type,
    )
    session.add(row)
    session.flush()
    return row


def test_organization_merge_preserves_aliases_metadata_type_and_primary_substrate() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        organization_id, stylebook_id, project_id = _seed(session)
        source = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Chicago Transit Authority",
            organization_type="public_services",
        )
        target = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="CTA",
            organization_type=None,
        )
        substrate = SubstrateOrganization(
            project_id=project_id,
            name="Chicago Transit Authority",
            normalized_name="chicago transit authority",
            organization_type="public_services",
            stylebook_organization_canonical_id=str(source.id),
            canonical_link_status="linked",
        )
        session.add(substrate)
        session.flush()
        source.primary_substrate_organization_id = int(substrate.id)  # type: ignore[arg-type]
        session.add(source)
        session.add(
            StylebookOrganizationAlias(
                organization_canonical_id=str(source.id),
                alias_text="C.T.A.",
                normalized_alias="c t a",
                provenance="stylebook_ui_manual",
                suppressed=False,
            )
        )
        session.add(
            StylebookOrganizationAlias(
                organization_canonical_id=str(source.id),
                alias_text="Old CTA",
                normalized_alias="old cta",
                provenance="stylebook_ui_manual",
                suppressed=True,
            )
        )
        session.add(
            StylebookOrganizationMeta(
                project_id=project_id,
                stylebook_organization_canonical_id=str(source.id),
                meta_type="wikidata",
                value_type="text",
                value_text="Q6583",
                edited=True,
            )
        )
        session.add(
            StylebookOrganizationMeta(
                project_id=project_id,
                stylebook_organization_canonical_id=str(target.id),
                meta_type="wikidata",
                value_type="text",
                value_text="Q6583",
                added=True,
            )
        )
        session.commit()

        result = merge_organization_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
        )
        session.commit()

        assert result.organization_type == "public_services"
        assert session.get(StylebookOrganizationCanonical, str(source.id)) is None
        merged = session.get(StylebookOrganizationCanonical, str(target.id))
        assert merged is not None
        assert merged.organization_type == "public_services"
        assert merged.primary_substrate_organization_id == substrate.id
        session.refresh(substrate)
        assert substrate.stylebook_organization_canonical_id == str(target.id)

        aliases = session.exec(
            select(StylebookOrganizationAlias).where(
                StylebookOrganizationAlias.organization_canonical_id == str(target.id)
            )
        ).all()
        aliases_by_norm = {row.normalized_alias: row for row in aliases}
        assert aliases_by_norm["c t a"].provenance == "stylebook_ui_manual"
        assert aliases_by_norm["old cta"].suppressed is True
        assert "chicago transit authority" in aliases_by_norm

        meta = session.exec(
            select(StylebookOrganizationMeta).where(
                StylebookOrganizationMeta.stylebook_organization_canonical_id == str(target.id),
                StylebookOrganizationMeta.meta_type == "wikidata",
            )
        ).one()
        assert meta.value_text == "Q6583"
        assert meta.added is True
        assert meta.edited is True


def test_organization_merge_transfers_aliases_before_relinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        organization_id, stylebook_id, project_id = _seed(session)
        source = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Source Organization",
            organization_type="company",
        )
        target = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Target Organization",
            organization_type="company",
        )
        session.add(
            SubstrateOrganization(
                project_id=project_id,
                name="Source-Only Alias",
                normalized_name="source only alias",
                organization_type="company",
                stylebook_organization_canonical_id=str(source.id),
                canonical_link_status="linked",
            )
        )
        session.add(
            StylebookOrganizationAlias(
                organization_canonical_id=str(source.id),
                alias_text="Source-Only Alias",
                normalized_alias="source only alias",
                provenance="stylebook_cleanup_ai_review",
                suppressed=False,
            )
        )
        session.add(
            StylebookOrganizationAlias(
                organization_canonical_id=str(source.id),
                alias_text="Source Organization",
                normalized_alias="source organization",
                provenance="substrate_ingest",
                suppressed=True,
            )
        )
        session.commit()

        original_link = organization_merge.link_substrate_to_canonical_atomic
        alias_transfer_observed = False

        def assert_aliases_transferred_before_link(*args: object, **kwargs: object) -> bool:
            nonlocal alias_transfer_observed
            source_aliases = session.exec(
                select(StylebookOrganizationAlias).where(
                    StylebookOrganizationAlias.organization_canonical_id == str(source.id)
                )
            ).all()
            target_alias = session.exec(
                select(StylebookOrganizationAlias).where(
                    StylebookOrganizationAlias.organization_canonical_id == str(target.id),
                    StylebookOrganizationAlias.normalized_alias == "source only alias",
                )
            ).first()
            assert source_aliases == []
            assert target_alias is not None
            alias_transfer_observed = True
            return original_link(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(
            organization_merge,
            "link_substrate_to_canonical_atomic",
            assert_aliases_transferred_before_link,
        )
        merge_organization_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
        )
        session.commit()

        assert alias_transfer_observed
        transferred_alias = session.exec(
            select(StylebookOrganizationAlias).where(
                StylebookOrganizationAlias.organization_canonical_id == str(target.id),
                StylebookOrganizationAlias.normalized_alias == "source only alias",
            )
        ).one()
        assert transferred_alias.provenance == "stylebook_cleanup_ai_review"
        suppressed_source_label = session.exec(
            select(StylebookOrganizationAlias).where(
                StylebookOrganizationAlias.organization_canonical_id == str(target.id),
                StylebookOrganizationAlias.normalized_alias == "source organization",
            )
        ).one()
        assert suppressed_source_label.suppressed is True


def test_organization_merge_refuses_conflicting_metadata_before_relinking() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        organization_id, stylebook_id, project_id = _seed(session)
        source = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Source",
            organization_type="company",
        )
        target = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Target",
            organization_type="company",
        )
        substrate = SubstrateOrganization(
            project_id=project_id,
            name="Source",
            normalized_name="source",
            organization_type="company",
            stylebook_organization_canonical_id=str(source.id),
            canonical_link_status="linked",
        )
        session.add(substrate)
        session.add_all(
            [
                StylebookOrganizationMeta(
                    project_id=project_id,
                    stylebook_organization_canonical_id=str(source.id),
                    meta_type="wikidata",
                    value_type="text",
                    value_text="Q1",
                ),
                StylebookOrganizationMeta(
                    project_id=project_id,
                    stylebook_organization_canonical_id=str(target.id),
                    meta_type="wikidata",
                    value_type="text",
                    value_text="Q2",
                ),
            ]
        )
        session.commit()

        with pytest.raises(ValueError, match="metadata conflict"):
            merge_organization_canonical_into(
                session,
                stylebook_id=stylebook_id,
                organization_id=organization_id,
                source_canonical_id=str(source.id),
                target_canonical_id=str(target.id),
            )
        session.rollback()

        session.refresh(substrate)
        assert substrate.stylebook_organization_canonical_id == str(source.id)
        assert session.get(StylebookOrganizationCanonical, str(source.id)) is not None


def test_organization_merge_keeps_target_type_by_default_and_allows_override() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        organization_id, stylebook_id, _project_id = _seed(session)
        source = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="Chicago Teachers Union",
            organization_type="community_group",
        )
        target = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="CTU",
            organization_type="nonprofit",
        )
        session.commit()

        result = merge_organization_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            source_canonical_id=str(source.id),
            target_canonical_id=str(target.id),
        )
        session.commit()

        assert result.organization_type == "nonprofit"
        merged = session.get(StylebookOrganizationCanonical, str(target.id))
        assert merged is not None
        assert merged.organization_type == "nonprofit"

        override_source = _canonical(
            session,
            stylebook_id=stylebook_id,
            label="CTU Chicago",
            organization_type="community_group",
        )
        session.commit()

        override_result = merge_organization_canonical_into(
            session,
            stylebook_id=stylebook_id,
            organization_id=organization_id,
            source_canonical_id=str(override_source.id),
            target_canonical_id=str(target.id),
            resolved_organization_type="community_group",
        )
        session.commit()

        assert override_result.organization_type == "community_group"
        merged = session.get(StylebookOrganizationCanonical, str(target.id))
        assert merged is not None
        assert merged.organization_type == "community_group"
