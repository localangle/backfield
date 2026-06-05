"""District identity helpers + recall geometry gates for political_district / address rows."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldWorkspace,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_entities.canonical.jurisdiction import (
    district_identity_from_components,
    district_identity_key,
    normalize_district_number_token,
    stylebook_district_fields_from_components,
)
from backfield_entities.canonical.match_score import CanonicalMatchFeatures
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.entities.location.policy import (
    _address_neighborhood_geometry_demotes_recall,
    _political_district_recall_identity_preflight,
)
from sqlmodel import Session, SQLModel, create_engine


def _bootstrap(session: Session, *, org_slug: str) -> tuple[int, int]:
    org = BackfieldOrganization(name="Org", slug=org_slug)
    session.add(org)
    session.commit()
    session.refresh(org)
    oid = int(org.id)  # type: ignore[arg-type]
    sb = ensure_default_stylebook_for_organization(session, oid)
    sb_id = int(sb.id)  # type: ignore[arg-type]
    ws = BackfieldWorkspace(
        organization_id=oid, stylebook_id=sb_id, name="W", slug=f"wg-{org_slug}"
    )
    session.add(ws)
    session.commit()
    return oid, sb_id


def test_normalize_district_number_token_hyphen() -> None:
    assert normalize_district_number_token("4-2") == "4-2"
    assert normalize_district_number_token("08") == "08"


def test_district_identity_key_round_trip() -> None:
    comps = {
        "district": {"kind": "us_house", "number": "08"},
        "state": {"abbr": "MN"},
        "country": {"abbr": "US"},
    }
    ident = district_identity_from_components(comps)
    assert ident is not None
    assert district_identity_key(ident) == "US-US-HOUSE-MN-08"


def test_stylebook_district_fields_from_components() -> None:
    comps = {
        "district": {"kind": "ward", "number": "15"},
        "state": {"abbr": "IL"},
        "country": {"abbr": "US"},
    }
    fields = stylebook_district_fields_from_components(comps)
    assert fields["district_kind"] == "ward"
    assert fields["district_number"] == "15"
    assert fields["district_key"] == "US-WARD-IL-15"


def test_political_district_preflight_defers_when_no_matching_key(monkeypatch) -> None:
    monkeypatch.setenv("BACKFIELD_STRICT_CANONICAL_GATES", "1")
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        _, sb_id = _bootstrap(session, org_slug="pd-pf-1")
        canon = StylebookLocationCanonical(
            stylebook_id=sb_id,
            label="Ward 7, Chicago, IL",
            slug="ward-7-chi",
            location_type="political_district",
            district_key="US-WARD-IL-7",
            district_kind="ward",
            district_number="7",
            status="active",
        )
        session.add(canon)
        session.commit()
        session.refresh(canon)
        loc = SubstrateLocation(
            project_id=1,
            name="Ward 8, Chicago, IL",
            normalized_name="ward 8, chicago, il",
            location_type="political_district",
            status="resolved",
            canonical_link_status="unlinked",
            source_details_json={
                "place_extract_components": {
                    "district": {"kind": "ward", "number": "8"},
                    "city": "Chicago",
                    "state": {"abbr": "IL"},
                    "country": {"abbr": "US"},
                }
            },
            geometry_json={"type": "Point", "coordinates": [-87.6, 41.9]},
            identity_fingerprint="fp-pd-pf-1",
        )
        session.add(loc)
        session.commit()
        session.refresh(loc)
        entry = {"components": loc.source_details_json["place_extract_components"]}
        plan = _political_district_recall_identity_preflight(
            session,
            location=loc,
            entry=entry,
            recall=[(str(canon.id), 0.5)],
        )
        assert plan is not None
        assert plan.decision.value == "defer"
        assert any(
            isinstance(r, dict) and r.get("code") == "district_identity_mismatch"
            for r in plan.resolution_reasons
        )


def test_address_neighborhood_geometry_demotes_outside_bbox() -> None:
    loc = SubstrateLocation(
        location_type="address",
        geometry_json={"type": "Point", "coordinates": [-87.5, 41.9]},
    )
    gj: dict = {
        "type": "Polygon",
        "coordinates": [
            [
                [-88.1, 41.8],
                [-88.05, 41.8],
                [-88.05, 41.85],
                [-88.1, 41.85],
                [-88.1, 41.8],
            ]
        ],
    }
    canon = StylebookLocationCanonical(location_type="neighborhood", geometry_json=gj)
    feat = CanonicalMatchFeatures(
        canonical_id="c1",
        label="Far",
        normalized_aliases=(),
        geometry_json=gj,
    )
    assert _address_neighborhood_geometry_demotes_recall(loc, canon, feat) is True


def test_address_neighborhood_geometry_skips_without_point() -> None:
    loc = SubstrateLocation(
        location_type="address",
        geometry_json={"type": "Polygon", "coordinates": []},
    )
    gj = {
        "type": "Polygon",
        "coordinates": [
            [
                [-87.7, 41.85],
                [-87.5, 41.85],
                [-87.5, 41.95],
                [-87.7, 41.95],
                [-87.7, 41.85],
            ]
        ],
    }
    canon = StylebookLocationCanonical(location_type="neighborhood", geometry_json=gj)
    feat = CanonicalMatchFeatures(
        canonical_id="c1",
        label="Hood",
        normalized_aliases=(),
        geometry_json=gj,
    )
    assert _address_neighborhood_geometry_demotes_recall(loc, canon, feat) is False
