"""Org stylebook library: create, rename (with slug redirects), default, guarded delete."""

from __future__ import annotations

from backfield_db import (
    BackfieldWorkspace,
    Stylebook,
    StylebookActivity,
    StylebookBundleJob,
    StylebookCandidateAiReview,
    StylebookCleanupAiProposal,
    StylebookCleanupAiReview,
    StylebookCleanupCheckResult,
    StylebookCleanupCheckRun,
    StylebookCleanupDismissal,
    StylebookLocationAlias,
    StylebookLocationCanonical,
    StylebookLocationMeta,
    StylebookMembership,
    StylebookOrganizationAlias,
    StylebookOrganizationCanonical,
    StylebookOrganizationMeta,
    StylebookPersonAlias,
    StylebookPersonCanonical,
    StylebookPersonMeta,
    StylebookSlugRedirect,
    SubstrateLocation,
    SubstrateOrganization,
    SubstratePerson,
)
from sqlalchemy import delete, or_, update
from sqlmodel import Session, col, select

from backfield_entities.canonical.link import CANONICAL_LINK_PENDING
from backfield_entities.catalog.graph_stylebook_refs import reassign_stylebook_refs_in_org_graphs
from backfield_entities.catalog.stylebook_record_slug import allocate_unique_stylebook_slug


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
    # Insert without default flag so the partial unique index never sees two defaults at once.
    sb = Stylebook(
        organization_id=organization_id,
        slug=slug,
        name=name,
        is_default=False,
    )
    session.add(sb)
    session.flush()
    session.refresh(sb)
    if is_default and sb.id is not None:
        return set_org_default_stylebook(
            session,
            organization_id=organization_id,
            stylebook_id=int(sb.id),
        )
    return sb


def _org_default_stylebook_id(session: Session, organization_id: int) -> int | None:
    row = session.exec(
        select(Stylebook.id).where(
            Stylebook.organization_id == organization_id,
            Stylebook.is_default == True,  # noqa: E712
        )
    ).first()
    if row is None:
        return None
    return int(row)


def _reassign_workspaces_from_stylebook(
    session: Session,
    *,
    organization_id: int,
    from_stylebook_id: int,
    to_stylebook_id: int,
) -> int:
    """Point workspaces at ``to_stylebook_id`` when they still reference ``from_stylebook_id``."""
    if from_stylebook_id == to_stylebook_id:
        return 0
    rows = list(
        session.exec(
            select(BackfieldWorkspace).where(
                BackfieldWorkspace.organization_id == organization_id,
                BackfieldWorkspace.stylebook_id == int(from_stylebook_id),
            )
        ).all()
    )
    for ws in rows:
        ws.stylebook_id = int(to_stylebook_id)
        session.add(ws)
    if rows:
        session.flush()
    return len(rows)


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

    session.exec(
        update(Stylebook)
        .where(Stylebook.organization_id == organization_id)
        .values(is_default=False)
    )
    session.exec(
        update(Stylebook).where(Stylebook.id == int(stylebook_id)).values(is_default=True)
    )
    session.flush()
    session.refresh(target)
    return target


def _reset_substrate_links_for_stylebook_delete(
    session: Session,
    *,
    stylebook_id: int,
) -> None:
    """Clear substrate FKs/status before canonicals cascade-delete with the stylebook.

    Postgres sets canonical FKs to NULL on cascade, but would leave ``canonical_link_status``
    as ``linked``. Reset both sides explicitly for a consistent pending review state.
    """
    reason = [
        {
            "code": "reset_pending_after_stylebook_deleted",
            "deleted_stylebook_id": int(stylebook_id),
        }
    ]
    location_ids = list(
        session.exec(
            select(StylebookLocationCanonical.id).where(
                StylebookLocationCanonical.stylebook_id == stylebook_id
            )
        ).all()
    )
    if location_ids:
        session.exec(
            update(SubstrateLocation)
            .where(col(SubstrateLocation.stylebook_location_canonical_id).in_(location_ids))
            .values(
                stylebook_location_canonical_id=None,
                canonical_link_status=CANONICAL_LINK_PENDING,
                canonical_review_reasons_json=reason,
            )
        )
    person_ids = list(
        session.exec(
            select(StylebookPersonCanonical.id).where(
                StylebookPersonCanonical.stylebook_id == stylebook_id
            )
        ).all()
    )
    if person_ids:
        session.exec(
            update(SubstratePerson)
            .where(col(SubstratePerson.stylebook_person_canonical_id).in_(person_ids))
            .values(
                stylebook_person_canonical_id=None,
                canonical_link_status=CANONICAL_LINK_PENDING,
                canonical_review_reasons_json=reason,
            )
        )
    organization_ids = list(
        session.exec(
            select(StylebookOrganizationCanonical.id).where(
                StylebookOrganizationCanonical.stylebook_id == stylebook_id
            )
        ).all()
    )
    if organization_ids:
        session.exec(
            update(SubstrateOrganization)
            .where(
                col(SubstrateOrganization.stylebook_organization_canonical_id).in_(
                    organization_ids
                )
            )
            .values(
                stylebook_organization_canonical_id=None,
                canonical_link_status=CANONICAL_LINK_PENDING,
                canonical_review_reasons_json=reason,
            )
        )


def _clear_stylebook_fk_dependents(session: Session, *, stylebook_id: int) -> None:
    """Remove child rows whose FKs to ``stylebook`` are not ``ON DELETE CASCADE``.

    Membership and slug redirects cascade in Postgres. Activity, bundle jobs, cleanup
    workflow tables, and candidate AI reviews do not and must be cleared first.
    """
    sid = int(stylebook_id)
    # Child-before-parent: proposals → reviews; results → runs.
    session.exec(
        delete(StylebookCleanupAiProposal).where(StylebookCleanupAiProposal.stylebook_id == sid)
    )
    session.exec(
        delete(StylebookCleanupAiReview).where(StylebookCleanupAiReview.stylebook_id == sid)
    )
    session.exec(
        delete(StylebookCleanupCheckResult).where(StylebookCleanupCheckResult.stylebook_id == sid)
    )
    session.exec(
        delete(StylebookCleanupCheckRun).where(StylebookCleanupCheckRun.stylebook_id == sid)
    )
    session.exec(
        delete(StylebookCleanupDismissal).where(StylebookCleanupDismissal.stylebook_id == sid)
    )
    session.exec(
        delete(StylebookCandidateAiReview).where(StylebookCandidateAiReview.stylebook_id == sid)
    )
    session.exec(delete(StylebookActivity).where(StylebookActivity.stylebook_id == sid))
    session.exec(
        delete(StylebookBundleJob).where(
            or_(
                StylebookBundleJob.source_stylebook_id == sid,
                StylebookBundleJob.result_stylebook_id == sid,
            )
        )
    )
    # Cascaded in Postgres migrations; deleted explicitly for SQLite FK parity.
    session.exec(delete(StylebookMembership).where(StylebookMembership.stylebook_id == sid))
    session.exec(delete(StylebookSlugRedirect).where(StylebookSlugRedirect.stylebook_id == sid))


def _delete_stylebook_canonical_trees(session: Session, *, stylebook_id: int) -> None:
    """Delete canonicals (and alias/meta children) for this stylebook.

    Postgres cascades canonicals from ``stylebook``; aliases/meta cascade from
    canonicals. Explicit deletes keep SQLite FK tests and both engines aligned.
    """
    sid = int(stylebook_id)
    location_ids = list(
        session.exec(
            select(StylebookLocationCanonical.id).where(
                StylebookLocationCanonical.stylebook_id == sid
            )
        ).all()
    )
    if location_ids:
        session.exec(
            delete(StylebookLocationAlias).where(
                col(StylebookLocationAlias.location_canonical_id).in_(location_ids)
            )
        )
        session.exec(
            delete(StylebookLocationMeta).where(
                col(StylebookLocationMeta.stylebook_location_canonical_id).in_(location_ids)
            )
        )
        session.exec(
            delete(StylebookLocationCanonical).where(StylebookLocationCanonical.stylebook_id == sid)
        )

    person_ids = list(
        session.exec(
            select(StylebookPersonCanonical.id).where(StylebookPersonCanonical.stylebook_id == sid)
        ).all()
    )
    if person_ids:
        session.exec(
            delete(StylebookPersonAlias).where(
                col(StylebookPersonAlias.person_canonical_id).in_(person_ids)
            )
        )
        session.exec(
            delete(StylebookPersonMeta).where(
                col(StylebookPersonMeta.stylebook_person_canonical_id).in_(person_ids)
            )
        )
        session.exec(
            delete(StylebookPersonCanonical).where(StylebookPersonCanonical.stylebook_id == sid)
        )

    organization_ids = list(
        session.exec(
            select(StylebookOrganizationCanonical.id).where(
                StylebookOrganizationCanonical.stylebook_id == sid
            )
        ).all()
    )
    if organization_ids:
        session.exec(
            delete(StylebookOrganizationAlias).where(
                col(StylebookOrganizationAlias.organization_canonical_id).in_(organization_ids)
            )
        )
        session.exec(
            delete(StylebookOrganizationMeta).where(
                col(StylebookOrganizationMeta.stylebook_organization_canonical_id).in_(
                    organization_ids
                )
            )
        )
        session.exec(
            delete(StylebookOrganizationCanonical).where(
                StylebookOrganizationCanonical.stylebook_id == sid
            )
        )


def delete_stylebook(
    session: Session,
    stylebook_id: int,
    *,
    replacement_default_id: int | None = None,
) -> None:
    """Delete a stylebook when guards pass (see StylebookLibraryError).

    Workspaces still referencing this stylebook are repointed to the org default (or the
    replacement default when deleting the current default). Deleting the current default
    requires ``replacement_default_id`` for another book in the same org.

    Non-cascading dependents (activity, bundle jobs, cleanup/candidate review rows) are
    removed first. Linked substrate rows are reset to pending, then canonical trees are
    deleted before the catalog row itself.
    """
    book = session.get(Stylebook, stylebook_id)
    if book is None:
        raise StylebookLibraryError("stylebook not found")

    org_id = int(book.organization_id)
    all_ids = session.exec(select(Stylebook.id).where(Stylebook.organization_id == org_id)).all()
    if len(all_ids) <= 1:
        raise StylebookLibraryError("cannot delete the last stylebook for an organization")

    reassign_target_id: int | None = None
    if book.is_default:
        if replacement_default_id is None:
            raise StylebookLibraryError("replacement default stylebook is required")
        if replacement_default_id == stylebook_id:
            raise StylebookLibraryError("invalid replacement default stylebook")
        replacement = session.get(Stylebook, replacement_default_id)
        if replacement is None or int(replacement.organization_id) != org_id:
            raise StylebookLibraryError("replacement stylebook not found in this organization")
        reassign_target_id = int(replacement_default_id)
        session.exec(
            update(Stylebook).where(Stylebook.organization_id == org_id).values(is_default=False)
        )
        session.exec(
            update(Stylebook)
            .where(Stylebook.id == int(replacement_default_id))
            .values(is_default=True)
        )
        session.flush()
    else:
        reassign_target_id = _org_default_stylebook_id(session, org_id)

    if reassign_target_id is None:
        raise StylebookLibraryError("organization has no default stylebook to reassign workspaces")
    _reassign_workspaces_from_stylebook(
        session,
        organization_id=org_id,
        from_stylebook_id=int(stylebook_id),
        to_stylebook_id=int(reassign_target_id),
    )
    reassign_stylebook_refs_in_org_graphs(
        session,
        organization_id=org_id,
        from_stylebook_id=int(stylebook_id),
        to_stylebook_id=int(reassign_target_id),
    )

    _reset_substrate_links_for_stylebook_delete(session, stylebook_id=int(stylebook_id))
    _clear_stylebook_fk_dependents(session, stylebook_id=int(stylebook_id))
    _delete_stylebook_canonical_trees(session, stylebook_id=int(stylebook_id))
    session.flush()

    session.delete(book)
    session.flush()
