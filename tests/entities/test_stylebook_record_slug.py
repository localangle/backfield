"""Unit tests for stylebook catalog slugify and allocation."""

from __future__ import annotations

from backfield_db import (
    BackfieldOrganization,
    Stylebook,
    StylebookSlugRedirect,
)
from backfield_entities.stylebook_record_slug import (
    allocate_unique_stylebook_slug,
    slugify_stylebook_name,
)
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    engine = create_engine("sqlite://", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine


def test_slugify_basic() -> None:
    assert slugify_stylebook_name("  My Book!  ") == "my-book"
    assert slugify_stylebook_name("café") == "caf"


def test_slugify_empty_fallback() -> None:
    assert slugify_stylebook_name("@@@") == "stylebook"


def test_allocate_avoids_current_and_redirect_slugs() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o-slug")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]

        sb = Stylebook(
            organization_id=oid,
            slug="news-desk",
            name="News Desk",
            is_default=True,
        )
        session.add(sb)
        session.commit()
        session.refresh(sb)
        sb_id = int(sb.id)  # type: ignore[arg-type]

        s2 = allocate_unique_stylebook_slug(session, oid, "News Desk")
        assert s2 == "news-desk-2"

        session.add(
            StylebookSlugRedirect(
                organization_id=oid,
                stylebook_id=sb_id,
                old_slug="legacy-slug",
            )
        )
        session.commit()

        s3 = allocate_unique_stylebook_slug(session, oid, "Legacy Slug")
        assert s3 == "legacy-slug-2"


def test_allocate_ignore_current_row_when_renaming() -> None:
    engine = _engine()
    with Session(engine) as session:
        org = BackfieldOrganization(name="O", slug="o2")
        session.add(org)
        session.commit()
        session.refresh(org)
        oid = int(org.id)  # type: ignore[arg-type]
        sb = Stylebook(
            organization_id=oid,
            slug="alpha",
            name="Alpha",
            is_default=True,
        )
        session.add(sb)
        session.commit()
        session.refresh(sb)
        sid = int(sb.id)  # type: ignore[arg-type]

        out = allocate_unique_stylebook_slug(session, oid, "Alpha", ignore_stylebook_id=sid)
        assert out == "alpha"
