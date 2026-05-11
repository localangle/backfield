"""Org stylebook library: create, rename (with slug redirects), default, guarded delete."""

from __future__ import annotations

from backfield_db import BackfieldWorkspace, Stylebook, StylebookBundleJob, StylebookSlugRedirect
from sqlalchemy import delete, or_
from sqlmodel import Session, col, select

from backfield_stylebook.stylebook_record_slug import allocate_unique_stylebook_slug


class StylebookLibraryError(ValueError):
    """Invalid stylebook library operation (constraint, guard, or not found)."""


def resolve_stylebook_by_slug(
    session: Session,
    *,
    organization_id: int,
    slug: str,
) -> Stylebook | None:
    """Resolve a catalog slug to a Stylebook row, following slug redirect history."""
    row = session.exec(
        select(Stylebook).where(
            Stylebook.organization_id == organization_id,
            Stylebook.slug == slug,
        )
    ).first()
    if row is not None:
        return row
    redir = session.exec(
        select(StylebookSlugRedirect).where(
            StylebookSlugRedirect.organization_id == organization_id,
            StylebookSlugRedirect.old_slug == slug,
        )
    ).first()
    if redir is None:
        return None
    return session.get(Stylebook, redir.stylebook_id)


def create_stylebook_for_import(
    session: Session,
    *,
    organization_id: int,
    desired_name: str,
) -> Stylebook:
    """Create a stylebook from an import, suffixing the display name until unique in the org."""
    base = desired_name.strip()
    if not base:
        raise StylebookLibraryError("name is required")
    name = base
    n = 2
    while session.exec(
        select(Stylebook.id).where(
            Stylebook.organization_id == organization_id,
            Stylebook.name == name,
        )
    ).first():
        name = f"{base} ({n})"
        n += 1
    return create_stylebook(session, organization_id=organization_id, name=name, is_default=False)


def create_stylebook(
    session: Session,
    *,
    organization_id: int,
    name: str,
    is_default: bool = False,
) -> Stylebook:
    """Create a stylebook with generated slug; optionally make it the org default."""
    dup = session.exec(
        select(Stylebook.id).where(
            Stylebook.organization_id == organization_id,
            Stylebook.name == name,
        )
    ).first()
    if dup is not None:
        raise StylebookLibraryError("a stylebook with this name already exists in the organization")

    slug = allocate_unique_stylebook_slug(session, organization_id, name)
    if is_default:
        for sb in session.exec(
            select(Stylebook).where(Stylebook.organization_id == organization_id)
        ).all():
            sb.is_default = False
            session.add(sb)
        session.flush()

    sb = Stylebook(
        organization_id=organization_id,
        slug=slug,
        name=name,
        is_default=is_default,
    )
    session.add(sb)
    session.flush()
    session.refresh(sb)
    return sb


def rename_stylebook(session: Session, *, stylebook_id: int, new_name: str) -> Stylebook:
    """Rename display name; regenerate slug and record redirect row when slug changes."""
    book = session.get(Stylebook, stylebook_id)
    if book is None:
        raise StylebookLibraryError("stylebook not found")

    if book.name == new_name:
        return book

    dup = session.exec(
        select(Stylebook.id).where(
            Stylebook.organization_id == book.organization_id,
            Stylebook.name == new_name,
            col(Stylebook.id) != stylebook_id,
        )
    ).first()
    if dup is not None:
        raise StylebookLibraryError("a stylebook with this name already exists in the organization")

    old_slug = str(book.slug)
    new_slug = allocate_unique_stylebook_slug(
        session,
        int(book.organization_id),
        new_name,
        ignore_stylebook_id=stylebook_id,
    )

    if new_slug != old_slug:
        session.add(
            StylebookSlugRedirect(
                organization_id=int(book.organization_id),
                stylebook_id=int(stylebook_id),
                old_slug=old_slug,
            )
        )

    book.name = new_name
    book.slug = new_slug
    session.add(book)
    session.flush()
    session.refresh(book)
    return book


def set_org_default_stylebook(
    session: Session,
    *,
    organization_id: int,
    stylebook_id: int,
) -> Stylebook:
    """Mark one stylebook as default for the org."""
    target = session.get(Stylebook, stylebook_id)
    if target is None:
        raise StylebookLibraryError("stylebook not found")
    if int(target.organization_id) != organization_id:
        raise StylebookLibraryError("stylebook does not belong to this organization")

    # Clear defaults first so SQLite's partial unique index never sees two defaults at once.
    for sb in session.exec(
        select(Stylebook).where(Stylebook.organization_id == organization_id)
    ).all():
        sb.is_default = False
        session.add(sb)
    session.flush()
    target.is_default = True
    session.add(target)
    session.flush()
    session.refresh(target)
    return target


def delete_stylebook(
    session: Session,
    stylebook_id: int,
    *,
    replacement_default_id: int | None = None,
) -> None:
    """Delete a stylebook when guards pass (see StylebookLibraryError).

    Workspaces still referencing this stylebook cannot be deleted (RESTRICT). Deleting the
    current default requires ``replacement_default_id`` for another book in the same org.
    """
    book = session.get(Stylebook, stylebook_id)
    if book is None:
        raise StylebookLibraryError("stylebook not found")

    org_id = int(book.organization_id)
    all_ids = session.exec(select(Stylebook.id).where(Stylebook.organization_id == org_id)).all()
    if len(all_ids) <= 1:
        raise StylebookLibraryError("cannot delete the last stylebook for an organization")

    ws_hit = session.exec(
        select(BackfieldWorkspace.id)
        .where(BackfieldWorkspace.stylebook_id == stylebook_id)
        .limit(1)
    ).first()
    if ws_hit is not None:
        raise StylebookLibraryError(
            "cannot delete a stylebook that is still assigned to a workspace; "
            "reassign workspaces first",
        )

    if book.is_default:
        if replacement_default_id is None:
            raise StylebookLibraryError("replacement default stylebook is required")
        if replacement_default_id == stylebook_id:
            raise StylebookLibraryError("invalid replacement default stylebook")
        replacement = session.get(Stylebook, replacement_default_id)
        if replacement is None or int(replacement.organization_id) != org_id:
            raise StylebookLibraryError("replacement stylebook not found in this organization")

        for sb in session.exec(select(Stylebook).where(Stylebook.organization_id == org_id)).all():
            sb.is_default = False
            session.add(sb)
        session.flush()
        replacement.is_default = True
        session.add(replacement)
        session.flush()

    # Async bundle jobs reference this stylebook; remove them so FK does not block delete.
    session.exec(
        delete(StylebookBundleJob).where(
            or_(
                StylebookBundleJob.source_stylebook_id == stylebook_id,
                StylebookBundleJob.result_stylebook_id == stylebook_id,
            )
        )
    )
    session.flush()

    session.delete(book)
    session.flush()
