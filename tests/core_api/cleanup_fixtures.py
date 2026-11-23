"""Shared fixtures and seed helpers for the keyed cleanup API tests."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import date

import pytest
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    BackfieldWorkspace,
    Stylebook,
    SubstrateArticle,
)
from backfield_entities.catalog.bootstrap import ensure_default_stylebook_for_organization
from backfield_entities.cleanup.entity_models import EntityName, cleanup_entity_models
from core_api.deps import get_session
from core_api.main import app
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from tests.core_api.auth_helpers import attach_test_engine, seed_first_admin
from tests.project_helpers import project_ownership_fields

CLEANUP_BASE = "/public/v1/projects/general/stylebooks/default/cleanup"


@dataclass(frozen=True)
class CleanupWorld:
    """Ids of the rows every cleanup test starts with."""

    organization_id: int
    stylebook_id: int
    project_id: int
    second_project_id: int
    foreign_stylebook_id: int


@dataclass(frozen=True)
class SeededEntity:
    canonical_id: str
    substrate_id: int


@pytest.fixture
def cleanup_engine(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'cleanup-api-test.db'}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture
def cleanup_world(cleanup_engine) -> CleanupWorld:
    """One organization with two projects sharing the default Stylebook, plus a foreign one."""
    with Session(cleanup_engine) as s:
        org = BackfieldOrganization(name="Backfield", slug="default")
        s.add(org)
        s.commit()
        s.refresh(org)
        organization_id = int(org.id)  # type: ignore[arg-type]
        stylebook = ensure_default_stylebook_for_organization(s, organization_id)
        workspace = BackfieldWorkspace(
            organization_id=organization_id,
            stylebook_id=int(stylebook.id),  # type: ignore[arg-type]
            name="Default Workspace",
            slug="default",
        )
        s.add(workspace)
        s.commit()
        s.refresh(workspace)
        project_ids: list[int] = []
        for name, slug in (("General", "general"), ("Second", "second")):
            project = BackfieldProject(
                **project_ownership_fields(s, organization_id, workspace_id=int(workspace.id)),
                name=name,
                slug=slug,
                organization_id=organization_id,
                workspace_id=int(workspace.id),
            )
            s.add(project)
            s.flush()
            project_ids.append(int(project.id))  # type: ignore[arg-type]
        other_org = BackfieldOrganization(name="Other Org", slug="other-org")
        s.add(other_org)
        s.flush()
        foreign = Stylebook(
            organization_id=int(other_org.id),  # type: ignore[arg-type]
            slug="foreign-stylebook",
            name="Foreign Stylebook",
            is_default=True,
        )
        s.add(foreign)
        s.commit()
        s.refresh(foreign)
        return CleanupWorld(
            organization_id=organization_id,
            stylebook_id=int(stylebook.id),  # type: ignore[arg-type]
            project_id=project_ids[0],
            second_project_id=project_ids[1],
            foreign_stylebook_id=int(foreign.id),  # type: ignore[arg-type]
        )


@pytest.fixture
def cleanup_session(cleanup_engine, cleanup_world) -> Generator[Session, None, None]:
    """A session for seeding rows; commit before calling the API."""
    with Session(cleanup_engine) as session:
        yield session


@pytest.fixture
def cleanup_client(cleanup_engine, cleanup_world) -> Generator[TestClient, None, None]:
    def get_test_session() -> Generator[Session, None, None]:
        with Session(cleanup_engine) as session:
            yield session

    app.dependency_overrides[get_session] = get_test_session
    try:
        yield attach_test_engine(TestClient(app), cleanup_engine)
    finally:
        app.dependency_overrides.clear()


def create_cleanup_key(
    client: TestClient,
    *,
    credential_type: str = "user",
    scopes: list[str] | None = None,
    project_id: int = 1,
) -> dict[str, str]:
    """Create a project API key as the first admin and return its bearer header."""
    try:
        seed_first_admin(client, "cleanup-admin@example.com", "cleanup-secret")
    except RuntimeError:
        pass  # a previous call in the same test already created the admin
    client.post(
        "/v1/auth/login",
        json={"email": "cleanup-admin@example.com", "password": "cleanup-secret"},
    )
    created = client.post(
        f"/v1/projects/{project_id}/api-keys",
        json={"credential_type": credential_type, "scopes": scopes or ["cleanup:read"]},
    )
    assert created.status_code == 200, created.text
    return {"Authorization": f"Bearer {created.json()['raw_key']}"}


def seed_substrate(
    session: Session,
    entity: EntityName,
    *,
    canonical_id: str,
    project_id: int,
    name: str,
) -> int:
    """Insert a project-level record linked to a canonical; return its id."""
    models = cleanup_entity_models(entity)
    substrate = models.substrate(
        project_id=project_id,
        name=name,
        normalized_name=name.lower(),
        **{models.substrate_canonical_column: canonical_id},
    )
    session.add(substrate)
    session.flush()
    return int(substrate.id)


def seed_entity(
    session: Session,
    entity: EntityName,
    *,
    stylebook_id: int,
    project_id: int,
    label: str,
    kind: str | None = None,
    aliases: tuple[str, ...] = (),
) -> SeededEntity:
    """Insert a canonical, one linked substrate row, and aliases."""
    models = cleanup_entity_models(entity)
    slug = label.lower().replace(" ", "-")
    canonical = models.canonical(stylebook_id=stylebook_id, label=label, slug=slug)
    if kind is not None:
        setattr(canonical, models.kind_column, kind)
    session.add(canonical)
    session.flush()
    substrate_id = seed_substrate(
        session, entity, canonical_id=str(canonical.id), project_id=project_id, name=label
    )
    for alias in aliases:
        session.add(
            models.alias(
                **{models.alias_canonical_column: canonical.id},
                alias_text=alias,
                normalized_alias=alias.lower(),
                provenance="ingest",
            )
        )
    session.commit()
    return SeededEntity(canonical_id=str(canonical.id), substrate_id=substrate_id)


def seed_article(
    session: Session,
    *,
    project_id: int,
    headline: str,
    text: str = "",
    pub_date: date | None = None,
    url: str | None = None,
) -> int:
    article = SubstrateArticle(
        project_id=project_id,
        headline=headline,
        text=text or headline,
        pub_date=pub_date,
        url=url,
    )
    session.add(article)
    session.commit()
    return int(article.id)  # type: ignore[arg-type]


def seed_mention(
    session: Session,
    entity: EntityName,
    *,
    substrate_id: int,
    article_id: int,
    mention_text: str,
    start_char: int | None = None,
    end_char: int | None = None,
    quote_text: str | None = None,
    deleted: bool = False,
) -> int:
    """Insert one mention and a single occurrence; return the mention id."""
    models = cleanup_entity_models(entity)
    mention = models.mention(
        article_id=article_id,
        deleted=deleted,
        **{models.mention_substrate_column: substrate_id},
    )
    session.add(mention)
    session.flush()
    session.add(
        models.occurrence(
            **{models.occurrence_mention_column: mention.id},
            mention_text=mention_text,
            quote_text=quote_text,
            start_char=start_char,
            end_char=end_char,
            occurrence_order=0,
        )
    )
    session.commit()
    return int(mention.id)
