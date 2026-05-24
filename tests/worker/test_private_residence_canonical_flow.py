"""Private-residence defer: auto-waive when auto-apply; UI suggestion when review-only."""

from __future__ import annotations

from backfield_db import AgateRun, SubstrateLocation
from backfield_stylebook.canonical_link import CANONICAL_LINK_PENDING, CANONICAL_LINK_WAIVED
from sqlmodel import Session, SQLModel, create_engine, select
from worker.substrate import persist_from_consolidated

CHICAGO_POINT = {"type": "Point", "coordinates": [-87.6298, 41.8781]}


def _bootstrap_project(session: Session, *, org_slug: str, project_slug: str) -> int:
    from backfield_db import BackfieldOrganization, BackfieldProject, BackfieldWorkspace
    from backfield_stylebook.bootstrap import ensure_default_stylebook_for_organization

    org = BackfieldOrganization(name="Org", slug=org_slug)
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = ensure_default_stylebook_for_organization(session, oid)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    ws = BackfieldWorkspace(
        organization_id=oid,
        stylebook_id=sb_id,
        name="Workspace",
        slug="ws",
    )
    session.add(ws)
    session.commit()
    session.refresh(ws)

    proj = BackfieldProject(
        organization_id=oid,
        name="Proj",
        slug=project_slug,
        workspace_id=int(ws.id),  # type: ignore[arg-type]
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)

    return int(proj.id)  # type: ignore[arg-type]


def test_persist_private_residence_auto_apply_sets_waived() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-prv", project_slug="proj-prv")
        session.add(AgateRun(id="run-prv", graph_id="graph-1", status="pending"))
        session.commit()

        consolidated = {
            "text": "Police responded to the 500 block of Oak St.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [
                    {
                        "id": "addr:oak",
                        "original_text": "500 block of Oak St",
                        "location": "500 Oak St, Chicago, IL",
                        "type": "address",
                        "address_place_kind": "private_residence",
                        "geocode": {
                            "geocode_type": "pelias",
                            "result": {
                                "id": "pelias:500-oak",
                                "formatted_address": "500 Oak St, Chicago, IL, USA",
                                "geometry": CHICAGO_POINT,
                            },
                        },
                    }
                ],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-prv",
            consolidated=consolidated,
            db_output_params={
                "canonicalization_mode": "rules",
                "auto_apply_canonicalization": True,
            },
        )
        session.commit()

    with Session(engine) as session:
        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].canonical_link_status == CANONICAL_LINK_WAIVED
        raw = locs[0].canonical_review_reasons_json
        assert isinstance(raw, list)
        assert any(
            isinstance(x, dict) and x.get("code") == "private_place_or_residence" for x in raw
        )


def test_persist_private_residence_review_only_pending_with_defer_suggestion() -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        project_id = _bootstrap_project(session, org_slug="org-pr2", project_slug="proj-pr2")
        session.add(AgateRun(id="run-pr2", graph_id="graph-1", status="pending"))
        session.commit()

        consolidated = {
            "text": "Police responded to the 500 block of Oak St.",
            "places": {
                "areas": {
                    "states": [],
                    "counties": [],
                    "cities": [],
                    "neighborhoods": [],
                    "regions": [],
                    "other": [],
                },
                "points": [
                    {
                        "id": "addr:oak2",
                        "original_text": "500 block of Oak St",
                        "location": "500 Oak St, Chicago, IL",
                        "type": "address",
                        "address_place_kind": "private_residence",
                        "geocode": {
                            "geocode_type": "pelias",
                            "result": {
                                "id": "pelias:500-oak-2",
                                "formatted_address": "500 Oak St, Chicago, IL, USA",
                                "geometry": CHICAGO_POINT,
                            },
                        },
                    }
                ],
                "needs_review": [],
            },
        }

        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-1",
            run_id="run-pr2",
            consolidated=consolidated,
            db_output_params={
                "canonicalization_mode": "rules",
                "auto_apply_canonicalization": False,
            },
        )
        session.commit()

    with Session(engine) as session:
        locs = session.exec(select(SubstrateLocation)).all()
        assert len(locs) == 1
        assert locs[0].canonical_link_status == CANONICAL_LINK_PENDING
        raw = locs[0].canonical_review_reasons_json
        assert isinstance(raw, list)
        sug = next(
            (x for x in raw if isinstance(x, dict) and x.get("code") == "canonical_suggestion"),
            None,
        )
        assert sug is not None
        assert sug.get("suggested_action") == "defer"
