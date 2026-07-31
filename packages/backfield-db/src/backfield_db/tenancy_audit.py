"""Read-only preflight audit for project workspace and Stylebook ownership."""

from __future__ import annotations

import json
from collections import defaultdict
from enum import StrEnum

from pydantic import BaseModel, Field
from sqlalchemy import inspect, text
from sqlmodel import Session, select

from backfield_db.models import (
    AgateGraph,
    BackfieldWorkspace,
    Stylebook,
    StylebookLocationCanonical,
    StylebookOrganizationCanonical,
    StylebookPersonCanonical,
    SubstrateLocation,
    SubstrateOrganization,
    SubstratePerson,
)


class TenancyBlockerCode(StrEnum):
    ORPHAN_PROJECT = "orphan_project"
    PROJECT_WORKSPACE_ORGANIZATION_MISMATCH = "project_workspace_organization_mismatch"
    WORKSPACE_STYLEBOOK_ORGANIZATION_MISMATCH = "workspace_stylebook_organization_mismatch"
    PROJECT_STYLEBOOK_ORGANIZATION_MISMATCH = "project_stylebook_organization_mismatch"
    PROJECT_STYLEBOOK_UNRESOLVED = "project_stylebook_unresolved"
    GRAPH_SPEC_INVALID = "graph_spec_invalid"
    GRAPH_STYLEBOOK_CONFLICT = "graph_stylebook_conflict"
    GRAPH_MULTIPLE_STYLEBOOKS = "graph_multiple_stylebooks"
    LINKED_CANONICAL_STYLEBOOK_MISMATCH = "linked_canonical_stylebook_mismatch"
    DUPLICATE_PROJECT_SLUG = "duplicate_project_slug"


class TenancyEntityType(StrEnum):
    LOCATION = "location"
    PERSON = "person"
    ORGANIZATION = "organization"


_ENTITY_ID_SAMPLE_LIMIT = 5


class TenancyAuditBlocker(BaseModel):
    code: TenancyBlockerCode
    message: str
    organization_id: int | None = None
    project_id: int | None = None
    related_project_ids: list[int] = Field(default_factory=list)
    project_slug: str | None = None
    workspace_id: int | None = None
    stylebook_id: int | None = None
    expected_stylebook_id: int | None = None
    actual_stylebook_ids: list[int] = Field(default_factory=list)
    graph_id: str | None = None
    node_ids: list[str] = Field(default_factory=list)
    entity_type: TenancyEntityType | None = None
    entity_id: str | None = None
    affected_count: int | None = None
    sample_entity_ids: list[str] = Field(default_factory=list)


class TenancyAuditReport(BaseModel):
    ok: bool
    blocker_count: int
    blockers: list[TenancyAuditBlocker] = Field(default_factory=list)

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)


class ProjectAuditRow(BaseModel):
    id: int
    organization_id: int
    workspace_id: int | None
    stylebook_id: int | None
    name: str
    slug: str


def _load_projects(session: Session) -> list[ProjectAuditRow]:
    """Load projects from either side of the additive ``stylebook_id`` migration."""
    connection = session.connection()
    column_names = {
        str(column["name"]) for column in inspect(connection).get_columns("backfield_project")
    }
    stylebook_projection = (
        "stylebook_id" if "stylebook_id" in column_names else "NULL AS stylebook_id"
    )
    rows = session.execute(
        text(
            f"""
            SELECT id, organization_id, workspace_id, {stylebook_projection}, name, slug
            FROM backfield_project
            ORDER BY id
            """
        )
    ).mappings()
    return [ProjectAuditRow.model_validate(dict(row)) for row in rows]


def _project_label(project: ProjectAuditRow) -> str:
    return f"project {project.id} ({project.slug})"


def _organization_fallbacks(stylebooks: list[Stylebook]) -> dict[int, int]:
    by_organization: dict[int, list[Stylebook]] = defaultdict(list)
    for stylebook in stylebooks:
        by_organization[int(stylebook.organization_id)].append(stylebook)

    fallbacks: dict[int, int] = {}
    for organization_id, rows in by_organization.items():
        defaults = [row for row in rows if bool(row.is_default)]
        chosen: Stylebook | None = defaults[0] if len(defaults) == 1 else None
        if chosen is None and not defaults and len(rows) == 1:
            chosen = rows[0]
        if chosen is not None and chosen.id is not None:
            fallbacks[organization_id] = int(chosen.id)
    return fallbacks


def _proposed_project_stylebooks(
    projects: list[ProjectAuditRow],
    workspaces: dict[int, BackfieldWorkspace],
    stylebooks: dict[int, Stylebook],
    organization_fallbacks: dict[int, int],
) -> dict[int, int | None]:
    proposed: dict[int, int | None] = {}
    for project in projects:
        project_id = project.id
        if project.stylebook_id is not None:
            proposed[project_id] = int(project.stylebook_id)
            continue
        workspace = (
            workspaces.get(int(project.workspace_id))
            if project.workspace_id is not None
            else None
        )
        if workspace is not None and int(workspace.organization_id) == int(project.organization_id):
            stylebook = stylebooks.get(int(workspace.stylebook_id))
            if stylebook is not None and int(stylebook.organization_id) == int(
                project.organization_id
            ):
                proposed[project_id] = int(workspace.stylebook_id)
                continue
            proposed[project_id] = None
            continue
        proposed[project_id] = organization_fallbacks.get(int(project.organization_id))
    return proposed


def _duplicate_project_slug_blockers(
    projects: list[ProjectAuditRow],
) -> list[TenancyAuditBlocker]:
    grouped: dict[tuple[int, str], list[ProjectAuditRow]] = defaultdict(list)
    for project in projects:
        grouped[(int(project.organization_id), str(project.slug))].append(project)

    blockers: list[TenancyAuditBlocker] = []
    for (organization_id, slug), rows in grouped.items():
        if len(rows) < 2:
            continue
        project_ids = sorted(row.id for row in rows)
        blockers.append(
            TenancyAuditBlocker(
                code=TenancyBlockerCode.DUPLICATE_PROJECT_SLUG,
                message=(
                    f"organization {organization_id} has duplicate project slug {slug!r} "
                    f"on projects {project_ids}"
                ),
                organization_id=organization_id,
                related_project_ids=project_ids,
                project_slug=slug,
            )
        )
    return blockers


def _coerce_stylebook_id(raw: object) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        if raw != raw or raw % 1 != 0:
            return None
        return int(raw)
    if isinstance(raw, str):
        value = raw.strip()
        if value.isdigit():
            return int(value)
    return None


def _node_stylebook_refs(spec_json: str) -> tuple[list[tuple[str, int]], bool]:
    try:
        raw = json.loads(spec_json)
    except (TypeError, json.JSONDecodeError):
        return [], False
    if not isinstance(raw, dict):
        return [], False
    nodes = raw.get("nodes")
    if not isinstance(nodes, list):
        return [], True

    references: list[tuple[str, int]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("id")
        params = node.get("params")
        if not isinstance(node_id, str) or not isinstance(params, dict):
            continue
        stylebook_id = _coerce_stylebook_id(params.get("stylebook_id"))
        if stylebook_id is None:
            stylebook_id = _coerce_stylebook_id(params.get("stylebookId"))
        if stylebook_id is None:
            continue
        references.append((node_id, stylebook_id))
    return references, True


def _graph_blockers(
    graphs: list[AgateGraph],
    projects: dict[int, ProjectAuditRow],
    proposed_stylebooks: dict[int, int | None],
) -> list[TenancyAuditBlocker]:
    blockers: list[TenancyAuditBlocker] = []
    for graph in graphs:
        project = projects.get(int(graph.project_id))
        if project is None:
            continue
        refs, valid_spec = _node_stylebook_refs(graph.spec_json)
        if not valid_spec:
            blockers.append(
                TenancyAuditBlocker(
                    code=TenancyBlockerCode.GRAPH_SPEC_INVALID,
                    message=f"graph {graph.id} has invalid JSON and cannot be audited",
                    organization_id=int(project.organization_id),
                    project_id=project.id,
                    project_slug=str(project.slug),
                    graph_id=str(graph.id),
                )
            )
            continue

        stylebook_ids = sorted({stylebook_id for _, stylebook_id in refs})
        if len(stylebook_ids) > 1:
            blockers.append(
                TenancyAuditBlocker(
                    code=TenancyBlockerCode.GRAPH_MULTIPLE_STYLEBOOKS,
                    message=f"graph {graph.id} references several Stylebooks: {stylebook_ids}",
                    organization_id=int(project.organization_id),
                    project_id=project.id,
                    project_slug=str(project.slug),
                    expected_stylebook_id=proposed_stylebooks.get(project.id),
                    actual_stylebook_ids=stylebook_ids,
                    graph_id=str(graph.id),
                    node_ids=[node_id for node_id, _ in refs],
                )
            )

        expected = proposed_stylebooks.get(project.id)
        conflicts = [(node_id, sid) for node_id, sid in refs if sid != expected]
        if conflicts:
            actual = sorted({sid for _, sid in conflicts})
            blockers.append(
                TenancyAuditBlocker(
                    code=TenancyBlockerCode.GRAPH_STYLEBOOK_CONFLICT,
                    message=(
                        f"graph {graph.id} references Stylebooks {actual}, "
                        f"not project Stylebook {expected}"
                    ),
                    organization_id=int(project.organization_id),
                    project_id=project.id,
                    project_slug=str(project.slug),
                    expected_stylebook_id=expected,
                    actual_stylebook_ids=actual,
                    graph_id=str(graph.id),
                    node_ids=[node_id for node_id, _ in conflicts],
                )
            )
    return blockers


def _linked_canonical_blocker(
    *,
    project: ProjectAuditRow,
    proposed_stylebook_id: int | None,
    actual_stylebook_id: int,
    entity_type: TenancyEntityType,
    entity_ids: set[int],
) -> TenancyAuditBlocker:
    ordered_entity_ids = sorted(entity_ids)
    affected_count = len(ordered_entity_ids)
    return TenancyAuditBlocker(
        code=TenancyBlockerCode.LINKED_CANONICAL_STYLEBOOK_MISMATCH,
        message=(
            f"{affected_count} linked {entity_type.value} row(s) use Stylebook "
            f"{actual_stylebook_id}, not project Stylebook {proposed_stylebook_id}"
        ),
        organization_id=int(project.organization_id),
        project_id=project.id,
        project_slug=str(project.slug),
        stylebook_id=actual_stylebook_id,
        expected_stylebook_id=proposed_stylebook_id,
        actual_stylebook_ids=[actual_stylebook_id],
        entity_type=entity_type,
        affected_count=affected_count,
        sample_entity_ids=[
            str(entity_id) for entity_id in ordered_entity_ids[:_ENTITY_ID_SAMPLE_LIMIT]
        ],
    )


def _record_linked_canonical_mismatch(
    groups: dict[tuple[int, TenancyEntityType, int, int | None], set[int]],
    *,
    projects: dict[int, ProjectAuditRow],
    proposed_stylebooks: dict[int, int | None],
    project_id: int,
    actual_stylebook_id: int,
    entity_type: TenancyEntityType,
    entity_id: int,
) -> None:
    project = projects.get(project_id)
    if project is None:
        return
    expected_stylebook_id = proposed_stylebooks.get(project.id)
    if expected_stylebook_id == actual_stylebook_id:
        return
    key = (project_id, entity_type, actual_stylebook_id, expected_stylebook_id)
    groups.setdefault(key, set()).add(entity_id)


def _linked_canonical_blockers(
    session: Session,
    projects: dict[int, ProjectAuditRow],
    proposed_stylebooks: dict[int, int | None],
) -> list[TenancyAuditBlocker]:
    groups: dict[tuple[int, TenancyEntityType, int, int | None], set[int]] = {}
    location_rows = session.exec(
        select(SubstrateLocation, StylebookLocationCanonical)
        .join(
            StylebookLocationCanonical,
            StylebookLocationCanonical.id
            == SubstrateLocation.stylebook_location_canonical_id,
        )
        .where(SubstrateLocation.canonical_link_status == "linked")
    ).all()
    person_rows = session.exec(
        select(SubstratePerson, StylebookPersonCanonical)
        .join(
            StylebookPersonCanonical,
            StylebookPersonCanonical.id == SubstratePerson.stylebook_person_canonical_id,
        )
        .where(SubstratePerson.canonical_link_status == "linked")
    ).all()
    organization_rows = session.exec(
        select(SubstrateOrganization, StylebookOrganizationCanonical)
        .join(
            StylebookOrganizationCanonical,
            StylebookOrganizationCanonical.id
            == SubstrateOrganization.stylebook_organization_canonical_id,
        )
        .where(SubstrateOrganization.canonical_link_status == "linked")
    ).all()

    for row, canonical in location_rows:
        if row.id is None:
            continue
        _record_linked_canonical_mismatch(
            groups,
            projects=projects,
            proposed_stylebooks=proposed_stylebooks,
            project_id=int(row.project_id),
            actual_stylebook_id=int(canonical.stylebook_id),
            entity_type=TenancyEntityType.LOCATION,
            entity_id=int(row.id),
        )
    for row, canonical in person_rows:
        if row.id is None:
            continue
        _record_linked_canonical_mismatch(
            groups,
            projects=projects,
            proposed_stylebooks=proposed_stylebooks,
            project_id=int(row.project_id),
            actual_stylebook_id=int(canonical.stylebook_id),
            entity_type=TenancyEntityType.PERSON,
            entity_id=int(row.id),
        )
    for row, canonical in organization_rows:
        if row.id is None:
            continue
        _record_linked_canonical_mismatch(
            groups,
            projects=projects,
            proposed_stylebooks=proposed_stylebooks,
            project_id=int(row.project_id),
            actual_stylebook_id=int(canonical.stylebook_id),
            entity_type=TenancyEntityType.ORGANIZATION,
            entity_id=int(row.id),
        )
    blockers: list[TenancyAuditBlocker] = []
    ordered_groups = sorted(
        groups.items(),
        key=lambda item: (
            item[0][0],
            item[0][1].value,
            item[0][2],
            item[0][3] if item[0][3] is not None else -1,
        ),
    )
    for (project_id, entity_type, actual, expected), entity_ids in ordered_groups:
        blockers.append(
            _linked_canonical_blocker(
                project=projects[project_id],
                proposed_stylebook_id=expected,
                actual_stylebook_id=actual,
                entity_type=entity_type,
                entity_ids=entity_ids,
            )
        )
    return blockers


def audit_tenancy(session: Session) -> TenancyAuditReport:
    """Inspect tenancy migration blockers without changing database state."""
    projects = _load_projects(session)
    workspaces = list(session.exec(select(BackfieldWorkspace)).all())
    stylebooks = list(session.exec(select(Stylebook)).all())
    graphs = list(session.exec(select(AgateGraph)).all())

    projects_by_id = {project.id: project for project in projects}
    workspaces_by_id = {
        int(workspace.id): workspace for workspace in workspaces if workspace.id is not None
    }
    stylebooks_by_id = {
        int(stylebook.id): stylebook for stylebook in stylebooks if stylebook.id is not None
    }
    proposed_stylebooks = _proposed_project_stylebooks(
        projects,
        workspaces_by_id,
        stylebooks_by_id,
        _organization_fallbacks(stylebooks),
    )

    blockers: list[TenancyAuditBlocker] = []
    for workspace in workspaces:
        stylebook = stylebooks_by_id.get(int(workspace.stylebook_id))
        if stylebook is None or int(stylebook.organization_id) != int(workspace.organization_id):
            blockers.append(
                TenancyAuditBlocker(
                    code=TenancyBlockerCode.WORKSPACE_STYLEBOOK_ORGANIZATION_MISMATCH,
                    message=(
                        f"workspace {workspace.id} belongs to organization "
                        f"{workspace.organization_id} but Stylebook "
                        f"{workspace.stylebook_id} does not"
                    ),
                    organization_id=int(workspace.organization_id),
                    workspace_id=int(workspace.id) if workspace.id is not None else None,
                    stylebook_id=int(workspace.stylebook_id),
                )
            )

    for project in projects:
        project_id = project.id
        if project.workspace_id is None:
            blockers.append(
                TenancyAuditBlocker(
                    code=TenancyBlockerCode.ORPHAN_PROJECT,
                    message=f"{_project_label(project)} has no workspace",
                    organization_id=int(project.organization_id),
                    project_id=project_id,
                    project_slug=str(project.slug),
                )
            )
        else:
            workspace = workspaces_by_id.get(int(project.workspace_id))
            if workspace is None or int(workspace.organization_id) != int(project.organization_id):
                blockers.append(
                    TenancyAuditBlocker(
                        code=TenancyBlockerCode.PROJECT_WORKSPACE_ORGANIZATION_MISMATCH,
                        message=(
                            f"{_project_label(project)} does not share an organization with "
                            f"workspace {project.workspace_id}"
                        ),
                        organization_id=int(project.organization_id),
                        project_id=project_id,
                        project_slug=str(project.slug),
                        workspace_id=int(project.workspace_id),
                    )
                )

        if project.stylebook_id is not None:
            stylebook = stylebooks_by_id.get(int(project.stylebook_id))
            if stylebook is None or int(stylebook.organization_id) != int(project.organization_id):
                blockers.append(
                    TenancyAuditBlocker(
                        code=TenancyBlockerCode.PROJECT_STYLEBOOK_ORGANIZATION_MISMATCH,
                        message=(
                            f"{_project_label(project)} does not share an organization with "
                            f"Stylebook {project.stylebook_id}"
                        ),
                        organization_id=int(project.organization_id),
                        project_id=project_id,
                        project_slug=str(project.slug),
                        stylebook_id=int(project.stylebook_id),
                    )
                )
        if proposed_stylebooks.get(project_id) is None:
            blockers.append(
                TenancyAuditBlocker(
                    code=TenancyBlockerCode.PROJECT_STYLEBOOK_UNRESOLVED,
                    message=f"{_project_label(project)} has no unambiguous Stylebook assignment",
                    organization_id=int(project.organization_id),
                    project_id=project_id,
                    project_slug=str(project.slug),
                )
            )

    blockers.extend(_duplicate_project_slug_blockers(projects))
    blockers.extend(_graph_blockers(graphs, projects_by_id, proposed_stylebooks))
    blockers.extend(_linked_canonical_blockers(session, projects_by_id, proposed_stylebooks))
    blockers.sort(
        key=lambda blocker: (
            blocker.code.value,
            blocker.organization_id or 0,
            blocker.project_id or 0,
            blocker.workspace_id or 0,
            blocker.graph_id or "",
            blocker.entity_id or "",
        )
    )
    return TenancyAuditReport(
        ok=not blockers,
        blocker_count=len(blockers),
        blockers=blockers,
    )
