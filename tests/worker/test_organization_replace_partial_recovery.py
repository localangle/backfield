"""Replace after a partial org persist must not raise StaleDataError."""

from __future__ import annotations

from backfield_db import (
    AgateRun,
    SubstrateOrganization,
    SubstrateOrganizationMention,
)
from sqlmodel import Session, SQLModel, col, create_engine, select
from worker.substrate.orchestration import persist_from_consolidated

from tests.worker.test_organization_substrate_persistence import (
    _bootstrap_project,
    _sample_organization_entry,
)


def test_organizations_replace_recovers_after_partial_machine_persist() -> None:
    """Simulate durable org rows left behind (e.g. mid-LLM commit), then replace."""
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    url = "https://example.com/organizations-partial-replace"

    with Session(engine) as session:
        project_id = _bootstrap_project(
            session,
            org_slug="org-organization-partial",
            project_slug="proj-organization-partial",
        )
        for run_id in ("run-org-p1", "run-org-p2"):
            session.add(AgateRun(id=run_id, graph_id="graph-org-partial", status="pending"))
        session.commit()

        # First pass persists two orgs (as if places/people finished and orgs partially wrote).
        persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-org-partial",
            run_id="run-org-p1",
            consolidated={
                "text": "Alpha Org and Beta Org appeared.",
                "url": url,
                "organizations": [
                    {**_sample_organization_entry(name="Alpha Org"), "type": "business"},
                    {**_sample_organization_entry(name="Beta Org"), "type": "nonprofit"},
                ],
            },
            db_output_params={"reconciliation_policy": "smart_merge"},
        )
        session.commit()

        # Leave rows durable, then authoritative replace with a type refinement for Alpha
        # (fingerprint change) and drop Beta — the recovery path that used to wedge.
        result = persist_from_consolidated(
            session,
            project_id=project_id,
            graph_id="graph-org-partial",
            run_id="run-org-p2",
            consolidated={
                "text": "Only Alpha Org remains, now typed as government.",
                "url": url,
                "organizations": [
                    {**_sample_organization_entry(name="Alpha Org"), "type": "government"},
                ],
            },
            db_output_params={"reconciliation_policy": "replace"},
        )
        session.commit()

        summary = next(item for item in result.domain_summaries if item.domain == "organizations")
        assert summary.policy == "replace"
        assert result.disposed_substrates >= 1

    with Session(engine) as session:
        names = {
            organization.normalized_name
            for organization in session.exec(select(SubstrateOrganization)).all()
        }
        assert "beta org" not in names
        assert "alpha org" in names
        alpha = session.exec(
            select(SubstrateOrganization).where(
                SubstrateOrganization.normalized_name == "alpha org"
            )
        ).one()
        assert alpha.organization_type == "government"
        active = session.exec(
            select(SubstrateOrganizationMention).where(
                SubstrateOrganizationMention.organization_id == int(alpha.id),
                col(SubstrateOrganizationMention.deleted).is_(False),
            )
        ).all()
        assert len(active) == 1
