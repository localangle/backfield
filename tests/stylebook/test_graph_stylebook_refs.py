"""Tests for graph spec stylebook reference scanning and validation."""

from __future__ import annotations

import json

from backfield_db import (
    AgateGraph,
    BackfieldOrganization,
    BackfieldProject,
    Stylebook,
)
from backfield_stylebook.graph_stylebook_refs import (
    STYLEBOOK_NODE_PARAM_KEY,
    StylebookGraphRefsError,
    count_stylebook_usage_in_graphs,
    iter_stylebook_refs_from_spec_dict,
    unique_stylebook_ids_from_spec_dict,
    validate_stylebook_refs_for_organization,
)
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def _minimal_spec_with_stylebook(node_id: str, stylebook_id: int) -> dict:
    return {
        "name": "g",
        "nodes": [
            {
                "id": node_id,
                "type": "db_output",
                "params": {STYLEBOOK_NODE_PARAM_KEY: stylebook_id},
            },
        ],
        "edges": [],
    }


def test_iter_legacy_stylebookId_param() -> None:
    """Older Geocode panels persisted camelCase ``stylebookId`` — still validated."""
    spec = {
        "name": "x",
        "nodes": [
            {"id": "a", "type": "GeocodeAgent", "params": {"stylebookId": 7}},
        ],
        "edges": [],
    }
    assert iter_stylebook_refs_from_spec_dict(spec) == [("a", 7)]
    assert unique_stylebook_ids_from_spec_dict(spec) == [7]


def test_iter_and_unique_ids() -> None:
    spec = {
        "name": "x",
        "nodes": [
            {"id": "a", "type": "t", "params": {STYLEBOOK_NODE_PARAM_KEY: 5}},
            {"id": "b", "type": "t", "params": {STYLEBOOK_NODE_PARAM_KEY: "5"}},
            {"id": "c", "type": "t", "params": {}},
        ],
        "edges": [],
    }
    refs = iter_stylebook_refs_from_spec_dict(spec)
    assert refs == [("a", 5), ("b", 5)]
    assert unique_stylebook_ids_from_spec_dict(spec) == [5]


def test_count_usage_across_graphs() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-gref")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]

        sb_a = Stylebook(
            organization_id=oid,
            slug="book-a",
            name="Book A",
            is_default=True,
        )
        sb_b = Stylebook(
            organization_id=oid,
            slug="book-b",
            name="Book B",
            is_default=False,
        )
        session.add(sb_a)
        session.add(sb_b)
        session.commit()
        session.refresh(sb_a)
        session.refresh(sb_b)
        aid = int(sb_a.id)  # type: ignore[arg-type]
        bid = int(sb_b.id)  # type: ignore[arg-type]

        proj = BackfieldProject(
            organization_id=oid,
            name="P",
            slug="p-gref",
            workspace_id=None,
        )
        session.add(proj)
        session.commit()
        session.refresh(proj)
        pid = int(proj.id)  # type: ignore[arg-type]

        spec1 = _minimal_spec_with_stylebook("n1", aid)
        spec2 = {
            "name": "g2",
            "nodes": [
                {
                    "id": "x",
                    "type": "t",
                    "params": {STYLEBOOK_NODE_PARAM_KEY: aid},
                },
                {
                    "id": "y",
                    "type": "t",
                    "params": {STYLEBOOK_NODE_PARAM_KEY: bid},
                },
            ],
            "edges": [],
        }
        session.add(
            AgateGraph(
                name="G1",
                spec_json=json.dumps(spec1),
                project_id=pid,
            )
        )
        session.add(
            AgateGraph(
                name="G2",
                spec_json=json.dumps(spec2),
                project_id=pid,
            )
        )
        session.commit()

        gc, nc = count_stylebook_usage_in_graphs(session, organization_id=oid, stylebook_id=aid)
        assert gc == 2
        assert nc == 2

        gc_b, nc_b = count_stylebook_usage_in_graphs(session, organization_id=oid, stylebook_id=bid)
        assert gc_b == 1
        assert nc_b == 1


def test_validate_missing_stylebook() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-val")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        spec = _minimal_spec_with_stylebook("n", 99999)
        try:
            validate_stylebook_refs_for_organization(session, organization_id=oid, spec=spec)
        except StylebookGraphRefsError:
            pass
        else:
            raise AssertionError("expected StylebookGraphRefsError")


def test_validate_wrong_org() -> None:
    engine = _engine()
    with Session(engine) as session:
        org1 = BackfieldOrganization(name="O1", slug="o1")
        org2 = BackfieldOrganization(name="O2", slug="o2")
        session.add(org1)
        session.add(org2)
        session.commit()
        session.refresh(org1)
        session.refresh(org2)
        o1 = int(org1.id)  # type: ignore[arg-type]
        o2 = int(org2.id)  # type: ignore[arg-type]

        sb = Stylebook(
            organization_id=o2,
            slug="other",
            name="Other",
            is_default=True,
        )
        session.add(sb)
        session.commit()
        session.refresh(sb)
        sid = int(sb.id)  # type: ignore[arg-type]

        spec = _minimal_spec_with_stylebook("n", sid)
        try:
            validate_stylebook_refs_for_organization(session, organization_id=o1, spec=spec)
        except StylebookGraphRefsError as e:
            assert "organization" in str(e).lower()
        else:
            raise AssertionError("expected StylebookGraphRefsError")


def test_validate_ok() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-ok")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        sb = Stylebook(
            organization_id=oid,
            slug="sb",
            name="SB",
            is_default=True,
        )
        session.add(sb)
        session.commit()
        session.refresh(sb)
        sid = int(sb.id)  # type: ignore[arg-type]
        spec = _minimal_spec_with_stylebook("n", sid)
        validate_stylebook_refs_for_organization(session, organization_id=oid, spec=spec)
