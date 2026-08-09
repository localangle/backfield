"""Project (and workspace→project) teardown helpers shared by Agate and Core APIs.

Deletes execution provenance, project-scoped Stylebook storage, substrate content, and
control-plane rows, then removes the project. Shared Stylebook canonicals are not touched.
Explicit child deletes keep Postgres and SQLite FK behavior aligned (see stylebook_library).
"""

from __future__ import annotations

from dataclasses import dataclass

from backfield_db import (
    AgateGraph,
    AgateNodeTiming,
    AgateProcessedItem,
    AgateRun,
    AgateS3IngestionLedger,
    BackfieldAiCallRecord,
    BackfieldAiDefaultModelRole,
    BackfieldAiProjectModelOverride,
    BackfieldApiCredential,
    BackfieldProject,
    BackfieldProjectMembership,
    BackfieldProjectSecret,
    BackfieldPublicIdempotencyRecord,
    BackfieldWorkspace,
    BackfieldWorkspaceMembership,
    StylebookActivity,
    StylebookCandidateAiReview,
    StylebookConnection,
    StylebookLocationMeta,
    StylebookOrganizationMeta,
    StylebookPersonMeta,
    SubstrateArticle,
    SubstrateArticleEmbedding,
    SubstrateArticleMeta,
    SubstrateCustomRecord,
    SubstrateImage,
    SubstrateImageEmbedding,
    SubstrateLocation,
    SubstrateLocationCache,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
    SubstrateLocationSemanticDocument,
    SubstrateOrganization,
    SubstrateOrganizationMention,
    SubstrateOrganizationMentionOccurrence,
    SubstrateOrganizationSemanticDocument,
    SubstratePerson,
    SubstratePersonMention,
    SubstratePersonMentionOccurrence,
    SubstratePersonSemanticDocument,
)
from sqlalchemy import delete, func, update
from sqlmodel import Session, col, select


class ProjectTeardownError(Exception):
    """Domain guard failure for project teardown (mapped to HTTP 400 by callers)."""


@dataclass(frozen=True)
class ProjectDeletePreview:
    project_id: int
    name: str
    slug: str
    flow_count: int
    run_count: int
    processed_item_count: int
    article_count: int
    api_credential_count: int
    secret_count: int


@dataclass(frozen=True)
class WorkspaceDeletePreview:
    workspace_id: int
    name: str
    slug: str
    project_count: int
    flow_count: int
    run_count: int
    processed_item_count: int
    article_count: int
    api_credential_count: int
    secret_count: int
    projects: list[ProjectDeletePreview]


def project_delete_preview(session: Session, project_id: int) -> ProjectDeletePreview | None:
    project = session.get(BackfieldProject, project_id)
    if project is None:
        return None
    pid = int(project_id)
    graph_ids = list(
        session.exec(select(AgateGraph.id).where(AgateGraph.project_id == pid)).all()
    )
    run_count = 0
    processed_item_count = 0
    if graph_ids:
        run_ids = list(
            session.exec(select(AgateRun.id).where(col(AgateRun.graph_id).in_(graph_ids))).all()
        )
        run_count = len(run_ids)
        if run_ids:
            processed_item_count = int(
                session.exec(
                    select(func.count())
                    .select_from(AgateProcessedItem)
                    .where(col(AgateProcessedItem.run_id).in_(run_ids))
                ).one()
            )
    article_count = int(
        session.exec(
            select(func.count())
            .select_from(SubstrateArticle)
            .where(SubstrateArticle.project_id == pid)
        ).one()
    )
    api_credential_count = int(
        session.exec(
            select(func.count())
            .select_from(BackfieldApiCredential)
            .where(BackfieldApiCredential.project_id == pid)
        ).one()
    )
    secret_count = int(
        session.exec(
            select(func.count())
            .select_from(BackfieldProjectSecret)
            .where(BackfieldProjectSecret.project_id == pid)
        ).one()
    )
    return ProjectDeletePreview(
        project_id=pid,
        name=str(project.name),
        slug=str(project.slug),
        flow_count=len(graph_ids),
        run_count=run_count,
        processed_item_count=processed_item_count,
        article_count=article_count,
        api_credential_count=api_credential_count,
        secret_count=secret_count,
    )


def workspace_delete_preview(
    session: Session,
    *,
    organization_id: int,
    workspace_id: int,
) -> WorkspaceDeletePreview | None:
    workspace = session.get(BackfieldWorkspace, workspace_id)
    if workspace is None or int(workspace.organization_id) != int(organization_id):
        return None
    project_ids = list(
        session.exec(
            select(BackfieldProject.id).where(
                BackfieldProject.organization_id == int(organization_id),
                BackfieldProject.workspace_id == int(workspace_id),
            )
        ).all()
    )
    projects: list[ProjectDeletePreview] = []
    for pid in project_ids:
        preview = project_delete_preview(session, int(pid))
        if preview is not None:
            projects.append(preview)
    return WorkspaceDeletePreview(
        workspace_id=int(workspace_id),
        name=str(workspace.name),
        slug=str(workspace.slug),
        project_count=len(projects),
        flow_count=sum(p.flow_count for p in projects),
        run_count=sum(p.run_count for p in projects),
        processed_item_count=sum(p.processed_item_count for p in projects),
        article_count=sum(p.article_count for p in projects),
        api_credential_count=sum(p.api_credential_count for p in projects),
        secret_count=sum(p.secret_count for p in projects),
        projects=projects,
    )


def delete_project(session: Session, project_id: int) -> None:
    """Hard-delete a project and its owned data. Caller must enforce auth and confirm_name.

    Raises ``ProjectTeardownError`` when the project is the reserved ``general`` slug or missing.
    """
    project = session.get(BackfieldProject, project_id)
    if project is None:
        raise ProjectTeardownError("project not found")
    if str(project.slug) == "general":
        raise ProjectTeardownError("cannot delete the General project")

    pid = int(project_id)
    _clear_project_non_cascading_dependents(session, project_id=pid)
    _delete_project_execution_records(session, project_id=pid)
    _delete_project_substrate_and_stylebook_storage(session, project_id=pid)
    _delete_project_control_plane_rows(session, project_id=pid)
    session.flush()
    session.delete(project)
    session.flush()


def delete_workspace(
    session: Session,
    *,
    organization_id: int,
    workspace_id: int,
) -> None:
    """Delete every project in the workspace, then the workspace row."""
    workspace = session.get(BackfieldWorkspace, workspace_id)
    if workspace is None or int(workspace.organization_id) != int(organization_id):
        raise ProjectTeardownError("workspace not found")

    project_ids = list(
        session.exec(
            select(BackfieldProject.id).where(
                BackfieldProject.organization_id == int(organization_id),
                BackfieldProject.workspace_id == int(workspace_id),
            )
        ).all()
    )
    for pid in project_ids:
        delete_project(session, int(pid))

    # Cascaded in Postgres; explicit for SQLite FK parity.
    session.exec(
        delete(BackfieldWorkspaceMembership).where(
            BackfieldWorkspaceMembership.workspace_id == int(workspace_id)
        )
    )
    session.delete(workspace)
    session.flush()


def _project_run_ids(session: Session, *, project_id: int) -> tuple[list[str], list[str]]:
    graph_ids = [
        str(gid)
        for gid in session.exec(
            select(AgateGraph.id).where(AgateGraph.project_id == project_id)
        ).all()
        if gid is not None
    ]
    if not graph_ids:
        return [], []
    run_ids = [
        str(rid)
        for rid in session.exec(
            select(AgateRun.id).where(col(AgateRun.graph_id).in_(graph_ids))
        ).all()
        if rid is not None
    ]
    return graph_ids, run_ids


def _delete_project_execution_records(session: Session, *, project_id: int) -> None:
    graph_ids, run_ids = _project_run_ids(session, project_id=project_id)
    if run_ids:
        # Drop article / custom-record / meta provenance that FKs to runs before run delete.
        session.exec(
            update(SubstrateArticle)
            .where(col(SubstrateArticle.source_run_id).in_(run_ids))
            .values(source_run_id=None, source_item_id=None)
        )
        session.exec(
            update(SubstrateArticleMeta)
            .where(col(SubstrateArticleMeta.source_run_id).in_(run_ids))
            .values(source_run_id=None)
        )
        session.exec(
            update(SubstrateCustomRecord)
            .where(col(SubstrateCustomRecord.source_run_id).in_(run_ids))
            .values(source_run_id=None)
        )
        session.exec(
            update(AgateS3IngestionLedger)
            .where(AgateS3IngestionLedger.project_id == project_id)
            .values(processed_item_id=None, flow_run_id=None)
        )
        session.exec(
            update(AgateProcessedItem)
            .where(col(AgateProcessedItem.run_id).in_(run_ids))
            .values(substrate_article_id=None, ingestion_ledger_id=None)
        )
        session.exec(delete(AgateNodeTiming).where(col(AgateNodeTiming.run_id).in_(run_ids)))
        session.exec(
            delete(AgateProcessedItem).where(col(AgateProcessedItem.run_id).in_(run_ids))
        )
        session.exec(
            delete(BackfieldPublicIdempotencyRecord).where(
                col(BackfieldPublicIdempotencyRecord.run_id).in_(run_ids)
            )
        )
        session.exec(delete(AgateRun).where(col(AgateRun.id).in_(run_ids)))

    if graph_ids:
        session.exec(delete(AgateGraph).where(col(AgateGraph.id).in_(graph_ids)))


def _clear_project_non_cascading_dependents(session: Session, *, project_id: int) -> None:
    """Rows whose FKs to project are NO ACTION / missing ondelete in models."""
    pid = int(project_id)
    session.exec(delete(BackfieldAiCallRecord).where(BackfieldAiCallRecord.project_id == pid))
    session.exec(
        delete(BackfieldAiProjectModelOverride).where(
            BackfieldAiProjectModelOverride.project_id == pid
        )
    )
    session.exec(
        delete(BackfieldAiDefaultModelRole).where(BackfieldAiDefaultModelRole.project_id == pid)
    )
    session.exec(delete(StylebookActivity).where(StylebookActivity.project_id == pid))
    session.exec(
        delete(StylebookCandidateAiReview).where(StylebookCandidateAiReview.project_id == pid)
    )
    session.exec(
        delete(SubstratePersonSemanticDocument).where(
            SubstratePersonSemanticDocument.project_id == pid
        )
    )
    session.exec(
        delete(SubstrateLocationSemanticDocument).where(
            SubstrateLocationSemanticDocument.project_id == pid
        )
    )
    session.exec(
        delete(SubstrateOrganizationSemanticDocument).where(
            SubstrateOrganizationSemanticDocument.project_id == pid
        )
    )


def _delete_project_substrate_and_stylebook_storage(session: Session, *, project_id: int) -> None:
    """Project-owned content and project-keyed Stylebook meta/connections (not canonicals)."""
    pid = int(project_id)

    session.exec(delete(StylebookConnection).where(StylebookConnection.project_id == pid))
    session.exec(delete(StylebookLocationMeta).where(StylebookLocationMeta.project_id == pid))
    session.exec(delete(StylebookPersonMeta).where(StylebookPersonMeta.project_id == pid))
    session.exec(
        delete(StylebookOrganizationMeta).where(StylebookOrganizationMeta.project_id == pid)
    )

    article_ids = list(
        session.exec(select(SubstrateArticle.id).where(SubstrateArticle.project_id == pid)).all()
    )
    location_ids = list(
        session.exec(select(SubstrateLocation.id).where(SubstrateLocation.project_id == pid)).all()
    )
    person_ids = list(
        session.exec(select(SubstratePerson.id).where(SubstratePerson.project_id == pid)).all()
    )
    organization_ids = list(
        session.exec(
            select(SubstrateOrganization.id).where(SubstrateOrganization.project_id == pid)
        ).all()
    )

    if article_ids:
        location_mention_ids = list(
            session.exec(
                select(SubstrateLocationMention.id).where(
                    col(SubstrateLocationMention.article_id).in_(article_ids)
                )
            ).all()
        )
        person_mention_ids = list(
            session.exec(
                select(SubstratePersonMention.id).where(
                    col(SubstratePersonMention.article_id).in_(article_ids)
                )
            ).all()
        )
        organization_mention_ids = list(
            session.exec(
                select(SubstrateOrganizationMention.id).where(
                    col(SubstrateOrganizationMention.article_id).in_(article_ids)
                )
            ).all()
        )
        if location_mention_ids:
            session.exec(
                delete(SubstrateLocationMentionOccurrence).where(
                    col(SubstrateLocationMentionOccurrence.location_mention_id).in_(
                        location_mention_ids
                    )
                )
            )
            session.exec(
                delete(SubstrateLocationMention).where(
                    col(SubstrateLocationMention.id).in_(location_mention_ids)
                )
            )
        if person_mention_ids:
            session.exec(
                delete(SubstratePersonMentionOccurrence).where(
                    col(SubstratePersonMentionOccurrence.person_mention_id).in_(person_mention_ids)
                )
            )
            session.exec(
                delete(SubstratePersonMention).where(
                    col(SubstratePersonMention.id).in_(person_mention_ids)
                )
            )
        if organization_mention_ids:
            session.exec(
                delete(SubstrateOrganizationMentionOccurrence).where(
                    col(SubstrateOrganizationMentionOccurrence.organization_mention_id).in_(
                        organization_mention_ids
                    )
                )
            )
            session.exec(
                delete(SubstrateOrganizationMention).where(
                    col(SubstrateOrganizationMention.id).in_(organization_mention_ids)
                )
            )

        image_ids = list(
            session.exec(
                select(SubstrateImage.id).where(col(SubstrateImage.article_id).in_(article_ids))
            ).all()
        )
        if image_ids:
            session.exec(
                delete(SubstrateImageEmbedding).where(
                    col(SubstrateImageEmbedding.image_id).in_(image_ids)
                )
            )
            session.exec(delete(SubstrateImage).where(col(SubstrateImage.id).in_(image_ids)))
        session.exec(
            delete(SubstrateArticleEmbedding).where(
                col(SubstrateArticleEmbedding.article_id).in_(article_ids)
            )
        )
        session.exec(
            delete(SubstrateArticleMeta).where(col(SubstrateArticleMeta.article_id).in_(article_ids))
        )
        session.exec(
            delete(SubstrateCustomRecord).where(
                col(SubstrateCustomRecord.article_id).in_(article_ids)
            )
        )
        session.exec(delete(SubstrateArticle).where(col(SubstrateArticle.id).in_(article_ids)))

    if location_ids:
        session.exec(delete(SubstrateLocation).where(col(SubstrateLocation.id).in_(location_ids)))
    if person_ids:
        session.exec(delete(SubstratePerson).where(col(SubstratePerson.id).in_(person_ids)))
    if organization_ids:
        session.exec(
            delete(SubstrateOrganization).where(col(SubstrateOrganization.id).in_(organization_ids))
        )
    session.exec(delete(SubstrateLocationCache).where(SubstrateLocationCache.project_id == pid))


def _delete_project_control_plane_rows(session: Session, *, project_id: int) -> None:
    pid = int(project_id)
    session.exec(
        delete(BackfieldPublicIdempotencyRecord).where(
            BackfieldPublicIdempotencyRecord.project_id == pid
        )
    )
    session.exec(delete(AgateS3IngestionLedger).where(AgateS3IngestionLedger.project_id == pid))
    session.exec(delete(BackfieldApiCredential).where(BackfieldApiCredential.project_id == pid))
    session.exec(delete(BackfieldProjectSecret).where(BackfieldProjectSecret.project_id == pid))
    session.exec(
        delete(BackfieldProjectMembership).where(BackfieldProjectMembership.project_id == pid)
    )
