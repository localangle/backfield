"""Golden-path tests for stylebook ZIP full bundle export/import."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    StylebookLocationMeta,
)
from backfield_stylebook.full_bundle import export_stylebook_bundle, import_stylebook_bundle
from sqlmodel import Session, SQLModel, create_engine, select


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def test_export_import_roundtrip_aliases_and_meta(tmp_path: Path) -> None:
    engine = _engine()
    zip_path = tmp_path / "bundle.zip"
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org", slug="org-bnd")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]

        sb = Stylebook(
            organization_id=oid,
            name="Source Book",
            slug="source-book",
            is_default=True,
        )
        session.add(sb)
        session.commit()
        session.refresh(sb)
        sb_id = int(sb.id)  # type: ignore[arg-type]

        proj = BackfieldProject(
            organization_id=oid,
            name="Alpha",
            slug="alpha-proj",
            workspace_id=None,
        )
        session.add(proj)
        session.commit()
        session.refresh(proj)
        pid = int(proj.id)  # type: ignore[arg-type]

        cid = str(uuid4())
        canon = StylebookLocationCanonical(
            id=cid,
            stylebook_id=sb_id,
            label="Elm Street",
            slug="elm-street",
            location_type="address",
            formatted_address="1 Elm St",
            status="active",
        )
        session.add(canon)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=cid,
                alias_text="Elm St",
                normalized_alias="elm st",
                provenance="test",
            )
        )
        session.add(
            StylebookLocationMeta(
                project_id=pid,
                stylebook_location_canonical_id=cid,
                meta_type="note",
                data_json={"k": "v"},
            )
        )
        session.commit()

        export_stylebook_bundle(
            session,
            organization_id=oid,
            stylebook_id=sb_id,
            zip_path=zip_path,
        )

    with Session(engine) as session:
        new_book, stats = import_stylebook_bundle(
            session,
            organization_id=oid,
            zip_path=zip_path,
            new_stylebook_name="Imported Book",
            project_mappings={"alpha-proj": pid},
        )
        new_id = int(new_book.id)  # type: ignore[arg-type]
        assert stats["canonicals"] >= 1
        assert stats["aliases"] >= 1
        assert stats["meta"] >= 1

        new_canon = session.exec(
            select(StylebookLocationCanonical).where(
                StylebookLocationCanonical.stylebook_id == new_id,
            )
        ).all()
        assert len(new_canon) == 1
        new_cid = str(new_canon[0].id)

        alias_rows = session.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == new_cid,
            )
        ).all()
        assert len(alias_rows) == 1

        meta_rows = session.exec(
            select(StylebookLocationMeta).where(
                StylebookLocationMeta.project_id == pid,
                StylebookLocationMeta.stylebook_location_canonical_id == new_cid,
            )
        ).all()
        assert len(meta_rows) == 1
