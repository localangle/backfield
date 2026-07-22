from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    SubstrateLocation,
)
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from sqlmodel import Session, SQLModel, create_engine
from worker.substrate.candidates.ai_review import _process_location_candidate_review


def _bootstrap(session: Session) -> tuple[int, int]:
    organization = BackfieldOrganization(name="Candidate Review", slug="candidate-review")
    session.add(organization)
    session.commit()
    session.refresh(organization)
    organization_id = int(organization.id)  # type: ignore[arg-type]
    stylebook = ensure_default_stylebook_for_organization(session, organization_id)
    stylebook_id = int(stylebook.id)  # type: ignore[arg-type]
    workspace = BackfieldWorkspace(
        organization_id=organization_id,
        stylebook_id=stylebook_id,
        name="Candidate Review",
        slug="candidate-review",
    )
    session.add(workspace)
    session.commit()
    session.refresh(workspace)
    project = BackfieldProject(
        organization_id=organization_id,
        workspace_id=int(workspace.id),  # type: ignore[arg-type]
        name="Candidate Review",
        slug="candidate-review",
    )
    session.add(project)
    session.commit()
    session.refresh(project)
    return int(project.id), stylebook_id  # type: ignore[arg-type]


def test_ai_review_links_near_location_despite_missing_geography(monkeypatch) -> None:
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        project_id, stylebook_id = _bootstrap(session)
        canonical = StylebookLocationCanonical(
            stylebook_id=stylebook_id,
            label="Robie House, Hyde Park, Chicago, IL",
            slug="robie-house-hyde-park-chicago-il",
            location_type="place",
            status="active",
        )
        session.add(canonical)
        session.commit()
        session.refresh(canonical)
        canonical_id = str(canonical.id)
        session.add(
            StylebookLocationAlias(
                location_canonical_id=canonical_id,
                alias_text=str(canonical.label),
                normalized_alias="robie house, hyde park, chicago, il",
                provenance="stylebook_ui_manual",
                suppressed=False,
            )
        )
        candidate = SubstrateLocation(
            project_id=project_id,
            name="Robie House, Chicago, IL",
            normalized_name="robie house, chicago, il",
            location_type="place",
            status="needs_review",
            canonical_link_status=CANONICAL_LINK_PENDING,
            geometry_json=None,
            identity_fingerprint="candidate-review-robie-house",
        )
        session.add(candidate)
        session.commit()
        session.refresh(candidate)
        candidate_id = int(candidate.id)  # type: ignore[arg-type]

    monkeypatch.setattr(
        "worker.substrate.canonical.adjudication.call_llm",
        lambda *_args, **_kwargs: (
            '{"decision":"link_existing",'
            f'"canonical_id":"{canonical_id}",'
            '"confidence":0.97,"same_identity":true,'
            '"conflicting_identity_evidence":false,'
            '"rationale":"The names identify the same landmark."}'
        ),
    )

    has_recommendation = _process_location_candidate_review(
        engine,
        stylebook_id=stylebook_id,
        project_id=project_id,
        location_id=candidate_id,
        model="gpt-test",
        model_config_id=None,
    )

    assert has_recommendation is True
    with Session(engine) as session:
        candidate = session.get(SubstrateLocation, candidate_id)
        assert candidate is not None
        assert candidate.stylebook_location_canonical_id is None
        assert candidate.canonical_link_status == CANONICAL_LINK_PENDING
        reasons = candidate.canonical_review_reasons_json
        assert isinstance(reasons, list)
        assert any(reason.get("code") == "geocode_quality_warning" for reason in reasons)
        assert any(reason.get("code") == "canonical_adjudication" for reason in reasons)
        assert any(
            reason.get("code") == "canonical_suggestion"
            and reason.get("source") == "candidate_ai_review"
            and reason.get("suggested_action") == "link_existing"
            and reason.get("stylebook_location_canonical_id") == canonical_id
            for reason in reasons
        )
