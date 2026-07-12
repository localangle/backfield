"""Golden-path tests for stylebook ZIP full bundle export/import (canonicals only)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from uuid import uuid4

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
    StylebookConnection,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    StylebookLocationMeta,
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    StylebookPersonAlias,
    StylebookPersonCanonical,
)
from backfield_entities.catalog.full_bundle import (
    BUNDLE_KIND_ALIAS_LOCATION,
    BUNDLE_KIND_CONNECTION,
    BUNDLE_KIND_LOCATION,
    BUNDLE_KIND_META_LOCATION,
    BUNDLE_KIND_ORGANIZATION,
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


def test_export_import_roundtrip_includes_organizations(tmp_path: Path) -> None:
    engine = _engine()
    zip_path = tmp_path / "bundle-organizations.zip"
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org Orgs", slug="org-orgs-bnd")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]

        sb = Stylebook(
            organization_id=oid,
            name="Organizations Book",
            slug="organizations-book",
            is_default=True,
        )
        session.add(sb)
        session.commit()
        session.refresh(sb)
        sb_id = int(sb.id)  # type: ignore[arg-type]

        org_id = str(uuid4())
        organization = StylebookOrganizationCanonical(
            id=org_id,
            stylebook_id=sb_id,
            label="City Hall",
            slug="city-hall",
            organization_type="government",
            status="active",
        )
        session.add(organization)
        session.commit()

        export_stylebook_bundle(
            session,
            organization_id=oid,
            stylebook_id=sb_id,
            zip_path=zip_path,
        )

    manifest = read_manifest_from_zip(zip_path)
    kinds = {fe["kind"] for fe in manifest["files"] if fe.get("kind") != "manifest"}
    assert BUNDLE_KIND_ORGANIZATION in kinds

    with Session(engine) as session:
        new_book, stats = import_stylebook_bundle(
            session,
            organization_id=oid,
            zip_path=zip_path,
            new_stylebook_name="Imported Organizations Book",
        )
        new_id = int(new_book.id)  # type: ignore[arg-type]
        assert stats["canonical_organizations"] == 1
        assert stats["canonicals"] == 1

        imported = session.exec(
            select(StylebookOrganizationCanonical).where(
                StylebookOrganizationCanonical.stylebook_id == new_id,
            )
        ).all()
        assert len(imported) == 1
        assert imported[0].label == "City Hall"
        assert imported[0].organization_type == "government"
        aliases = session.exec(
            select(StylebookOrganizationAlias).where(
                StylebookOrganizationAlias.organization_canonical_id == str(imported[0].id),
            )
        ).all()
        assert len(aliases) >= 1
        assert any(a.provenance == "stylebook_bundle_import" for a in aliases)


def test_export_import_roundtrip_includes_aliases_meta_connections(tmp_path: Path) -> None:
    engine = _engine()
    zip_path = tmp_path / "bundle-sidecars.zip"
    with Session(engine) as session:
        org = BackfieldOrganization(name="Org Sidecars", slug="org-sidecars-bnd")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]

        project = BackfieldProject(
            organization_id=oid,
            name="Demo Project",
            slug="demo-proj-sidecars",
        )
        session.add(project)
        session.commit()
        session.refresh(project)
        project_id = int(project.id)  # type: ignore[arg-type]

        sb = Stylebook(
            organization_id=oid,
            name="Sidecar Book",
            slug="sidecar-book",
            is_default=True,
        )
        session.add(sb)
        session.commit()
        session.refresh(sb)
        sb_id = int(sb.id)  # type: ignore[arg-type]

        loc_id = str(uuid4())
        person_id = str(uuid4())
        session.add(
            StylebookLocationCanonical(
                id=loc_id,
                stylebook_id=sb_id,
                label="City Hall",
                slug="city-hall",
                location_type="place",
                status="active",
            )
        )
        session.add(
            StylebookPersonCanonical(
                id=person_id,
                stylebook_id=sb_id,
                label="Jane Doe",
                slug="jane-doe",
                status="active",
            )
        )
        session.flush()
        session.add(
            StylebookLocationAlias(
                location_canonical_id=loc_id,
                alias_text="City Hall",
                normalized_alias="city hall",
                provenance="stylebook_ui_manual",
                suppressed=False,
            )
        )
        session.add(
            StylebookLocationAlias(
                location_canonical_id=loc_id,
                alias_text="Old City Hall",
                normalized_alias="old city hall",
                provenance="ingest_pipeline",
                suppressed=True,
            )
        )
        session.add(
            StylebookLocationMeta(
                project_id=project_id,
                stylebook_location_canonical_id=loc_id,
                meta_type="note",
                data_json={"body": "Landmark building"},
                added=True,
            )
        )
        session.add(
            StylebookConnection(
                project_id=project_id,
                from_entity_type="person",
                from_entity_id=person_id,
                to_entity_type="location",
                to_entity_id=loc_id,
                nature="works_at",
                description="Jane Doe works at City Hall.",
            )
        )
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
    assert BUNDLE_KIND_ALIAS_LOCATION in kinds
    assert BUNDLE_KIND_META_LOCATION in kinds
    assert BUNDLE_KIND_CONNECTION in kinds
    assert manifest["project_slices"]

    with Session(engine) as session:
        new_book, stats = import_stylebook_bundle(
            session,
            organization_id=oid,
            zip_path=zip_path,
            new_stylebook_name="Imported Sidecar Book",
            project_mappings={"demo-proj-sidecars": project_id},
        )
        new_id = int(new_book.id)  # type: ignore[arg-type]
        assert stats["aliases"] == 2
        assert stats["meta"] == 1
        assert stats["connections"] == 1

        imported_loc = session.exec(
            select(StylebookLocationCanonical).where(
                StylebookLocationCanonical.stylebook_id == new_id,
            )
        ).one()
        imported_person = session.exec(
            select(StylebookPersonCanonical).where(
                StylebookPersonCanonical.stylebook_id == new_id,
            )
        ).one()
        aliases = session.exec(
            select(StylebookLocationAlias).where(
                StylebookLocationAlias.location_canonical_id == str(imported_loc.id),
            )
        ).all()
        assert len(aliases) == 2
        assert any(a.normalized_alias == "old city hall" and a.suppressed for a in aliases)

        meta_rows = session.exec(
            select(StylebookLocationMeta).where(
                StylebookLocationMeta.stylebook_location_canonical_id == str(imported_loc.id),
            )
        ).all()
        assert len(meta_rows) == 1
        assert meta_rows[0].data_json == {"body": "Landmark building"}

        connections = session.exec(
            select(StylebookConnection).where(
                StylebookConnection.project_id == project_id,
                StylebookConnection.to_entity_id == str(imported_loc.id),
            )
        ).all()
        assert len(connections) == 1
        assert connections[0].from_entity_id == str(imported_person.id)
        assert connections[0].to_entity_id == str(imported_loc.id)
