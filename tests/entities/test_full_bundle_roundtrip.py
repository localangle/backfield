"""Golden-path tests for stylebook ZIP full bundle export/import (canonicals only)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from uuid import uuid4

from backfield_db import (
    BackfieldOrganization,
    Stylebook,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    StylebookPersonAlias,
    StylebookPersonCanonical,
)
from backfield_stylebook.full_bundle import (
    BUNDLE_KIND_LOCATION,
    BUNDLE_KIND_PERSON,
    BUNDLE_SCHEMA_VERSION,
    export_stylebook_bundle,
    import_stylebook_bundle,
    read_manifest_from_zip,
)
from sqlmodel import Session, SQLModel, create_engine, select


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def test_read_manifest_accepts_single_nested_bundle_folder(tmp_path: Path) -> None:
    """Manifest may live under one top-level directory; paths stay root-relative."""
    root_name = "b06657cd-4811-4725-9504-58fa31c37b0a"
    root = tmp_path / root_name
    root.mkdir()
    (root / "canonicals").mkdir()
    cid = str(uuid4())
    (root / "canonicals" / "part-00001.jsonl").write_text(
        json.dumps({"id": cid, "label": "Nested", "slug": "nested"}) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "files": [
            {
                "path": "canonicals/part-00001.jsonl",
                "kind": "canonical",
                "rows": 1,
                "sha256": "0" * 64,
            },
        ],
        "project_slices": [],
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    zip_path = tmp_path / "nested.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(root / "manifest.json", arcname=f"{root_name}/manifest.json")
        zf.write(
            root / "canonicals" / "part-00001.jsonl",
            arcname=f"{root_name}/canonicals/part-00001.jsonl",
        )

    loaded = read_manifest_from_zip(zip_path)
    assert loaded["schema_version"] == 1
    assert len(loaded["files"]) == 1


def test_export_import_roundtrip_canonicals_only(tmp_path: Path) -> None:
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
        session.commit()

        export_stylebook_bundle(
            session,
            organization_id=oid,
            stylebook_id=sb_id,
            zip_path=zip_path,
        )

    manifest = read_manifest_from_zip(zip_path)
    assert manifest["schema_version"] == BUNDLE_SCHEMA_VERSION
    kinds = {fe["kind"] for fe in manifest["files"] if fe.get("kind") != "manifest"}
    assert BUNDLE_KIND_LOCATION in kinds

    with Session(engine) as session:
        new_book, stats = import_stylebook_bundle(
            session,
            organization_id=oid,
            zip_path=zip_path,
            new_stylebook_name="Imported Book",
        )
        new_id = int(new_book.id)  # type: ignore[arg-type]
        assert stats["canonical_locations"] == 1
        assert stats["canonicals"] == 1

        new_canon = session.exec(
            select(StylebookLocationCanonical).where(
                StylebookLocationCanonical.stylebook_id == new_id,
            )
        ).all()
        assert len(new_canon) == 1
        assert str(new_canon[0].label) == "Elm Street"
        aliases = session.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == str(new_canon[0].id),
            )
        ).all()
        assert len(aliases) >= 1
        assert any(a.normalized_alias == "elm street" for a in aliases)


def test_export_import_roundtrip_includes_people(tmp_path: Path) -> None:
    engine = _engine()
    zip_path = tmp_path / "bundle-people.zip"
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org People", slug="org-people-bnd")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]

        sb = Stylebook(
            organization_id=oid,
            name="People Book",
            slug="people-book",
            is_default=True,
        )
        session.add(sb)
        session.commit()
        session.refresh(sb)
        sb_id = int(sb.id)  # type: ignore[arg-type]

        pid = str(uuid4())
        person = StylebookPersonCanonical(
            id=pid,
            stylebook_id=sb_id,
            label="Jane Doe",
            slug="jane-doe",
            title="Mayor",
            affiliation="City Hall",
            public_figure=True,
            person_type="official",
            sort_key="doe",
            status="active",
        )
        session.add(person)
        session.commit()

        export_stylebook_bundle(
            session,
            organization_id=oid,
            stylebook_id=sb_id,
            zip_path=zip_path,
        )

    manifest = read_manifest_from_zip(zip_path)
    kinds = {fe["kind"] for fe in manifest["files"] if fe.get("kind") != "manifest"}
    assert BUNDLE_KIND_PERSON in kinds

    with Session(engine) as session:
        new_book, stats = import_stylebook_bundle(
            session,
            organization_id=oid,
            zip_path=zip_path,
            new_stylebook_name="Imported People Book",
        )
        new_id = int(new_book.id)  # type: ignore[arg-type]
        assert stats["canonical_people"] == 1
        assert stats["canonicals"] == 1

        imported = session.exec(
            select(StylebookPersonCanonical).where(
                StylebookPersonCanonical.stylebook_id == new_id,
            )
        ).all()
        assert len(imported) == 1
        assert imported[0].label == "Jane Doe"
        assert imported[0].title == "Mayor"
        assert imported[0].sort_key == "doe"
        assert imported[0].public_figure is True
        aliases = session.exec(
            select(StylebookPersonAlias).where(
                StylebookPersonAlias.person_canonical_id == str(imported[0].id),
            )
        ).all()
        assert len(aliases) >= 1
        assert any(a.provenance == "stylebook_bundle_import" for a in aliases)
