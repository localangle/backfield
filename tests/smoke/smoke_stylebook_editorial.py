#!/usr/bin/env python3
"""Stylebook editorial review smoke with candidate assignment."""

from __future__ import annotations

import os
import sys
import uuid

import httpx
from _helpers import (
    assert_object,
    default_stylebook_for_org,
    delete_smoke_canonical,
    delete_smoke_substrate_rows,
    ensure_health,
    http_error_detail,
    keep_smoke_data,
    log,
    login_session_context,
    session_cookie_headers,
    smoke_db_session,
)
from backfield_db import (
    SubstrateArticle,
    SubstrateLocation,
    SubstrateLocationMention,
    SubstrateLocationMentionOccurrence,
)
from backfield_stylebook.canonical_link import CANONICAL_LINK_PENDING
from sqlmodel import select

AGATE_API_BASE = os.environ.get("AGATE_API_BASE", "http://localhost:8000")
STYLEBOOK_API_BASE = os.environ.get("STYLEBOOK_API_BASE", "http://localhost:8003")
CORE_API_BASE = os.environ.get("CORE_API_BASE", "http://localhost:8004")
SMOKE_EMAIL = os.environ.get("SMOKE_EMAIL", "").strip()
SMOKE_PASSWORD = os.environ.get("SMOKE_PASSWORD", "")
SMOKE_WORKSPACE_SLUG = os.environ.get("SMOKE_WORKSPACE_SLUG", "default").strip()
SMOKE_PROJECT_SLUG = os.environ.get("SMOKE_PROJECT_SLUG", "general").strip()


def _seed_pending_candidate(*, project_id: int, label: str) -> int:
    with smoke_db_session() as session:
        article = SubstrateArticle(
            project_id=project_id,
            headline=f"{label} article",
            text=f"We visited {label} during the editorial smoke.",
            url=f"https://example.com/{label.lower().replace(' ', '-')}",
        )
        session.add(article)
        session.flush()
        if article.id is None:
            raise RuntimeError("Article id missing during editorial seed")

        location = SubstrateLocation(
            project_id=project_id,
            name=label,
            normalized_name=label.strip().lower(),
            location_type="city",
            formatted_address=f"{label}, IL, USA",
            identity_fingerprint=f"smoke-editorial-{uuid.uuid4().hex}",
            stylebook_location_canonical_id=None,
            canonical_link_status=CANONICAL_LINK_PENDING,
        )
        session.add(location)
        session.flush()
        if location.id is None:
            raise RuntimeError("Location id missing during editorial seed")

        mention = SubstrateLocationMention(
            article_id=int(article.id),
            location_id=int(location.id),
            role_in_story="setting",
            nature="primary",
            needs_review=False,
            deleted=False,
        )
        session.add(mention)
        session.flush()
        if mention.id is None:
            raise RuntimeError("Mention id missing during editorial seed")

        occurrence = SubstrateLocationMentionOccurrence(
            location_mention_id=int(mention.id),
            mention_text=label,
            quote_text=f"We visited {label} during the editorial smoke.",
            occurrence_order=0,
            suppressed=False,
        )
        session.add(occurrence)
        session.commit()
        return int(location.id)


def main() -> int:
    if not SMOKE_EMAIL or not SMOKE_PASSWORD:
        raise RuntimeError("smoke-stylebook-editorial requires SMOKE_EMAIL and SMOKE_PASSWORD")

    ctx = login_session_context(
        core_base=CORE_API_BASE,
        email=SMOKE_EMAIL,
        password=SMOKE_PASSWORD,
        workspace_slug=SMOKE_WORKSPACE_SLUG,
        project_slug=SMOKE_PROJECT_SLUG,
    )
    headers = session_cookie_headers(ctx.session_token)
    ensure_health(
        agate_base=AGATE_API_BASE,
        stylebook_base=STYLEBOOK_API_BASE,
        core_base=CORE_API_BASE,
        agate_headers=headers,
        stylebook_headers=headers,
    )

    stylebook = default_stylebook_for_org(
        stylebook_base=STYLEBOOK_API_BASE,
        session_token=ctx.session_token,
        organization_id=ctx.organization_id,
    )
    stylebook_slug = str(stylebook["slug"])
    label = f"Smoke Editorial {uuid.uuid4().hex[:8]}"
    canonical_id: str | None = None
    candidate_id: int | None = None

    try:
        with httpx.Client(base_url=STYLEBOOK_API_BASE, timeout=15.0, headers=headers) as client:
            canonical = assert_object(
                client.post(
                    f"/v1/stylebooks/{stylebook_slug}/canonical-locations",
                    params={"project": ctx.project_slug},
                    json={"label": label, "location_type": "city"},
                ),
                "create editorial canonical",
            )
            canonical_id = str(canonical["id"])

            candidate_id = _seed_pending_candidate(project_id=ctx.project_id, label=label)

            open_queue = assert_object(
                client.get(
                    "/v1/candidates",
                    params={"project_slug": ctx.project_slug, "status": "open", "q": label},
                ),
                "list open candidates",
            )
            candidates = open_queue.get("candidates")
            if not isinstance(candidates, list) or not any(
                isinstance(row, dict) and int(row.get("id", -1)) == candidate_id
                for row in candidates
            ):
                raise RuntimeError(
                    f"Editorial candidate {candidate_id} not found in open queue: {open_queue}"
                )

            context = assert_object(
                client.get(
                    f"/v1/candidates/{candidate_id}/context",
                    params={"project_slug": ctx.project_slug},
                ),
                "candidate context",
            )
            examples = context.get("examples")
            if not isinstance(examples, list) or not examples:
                raise RuntimeError(f"Expected at least one candidate context example: {context}")

            suggestions = assert_object(
                client.get(
                    f"/v1/candidates/{candidate_id}/suggested-canonicals",
                    params={"project_slug": ctx.project_slug},
                ),
                "candidate suggestions",
            )
            suggestion_rows = suggestions.get("suggestions")
            if not isinstance(suggestion_rows, list):
                raise RuntimeError(f"Expected suggestions list: {suggestions}")

            linked = assert_object(
                client.post(
                    f"/v1/locations/{candidate_id}/link-canonical",
                    params={"project_slug": ctx.project_slug},
                    json={"stylebook_location_canonical_id": canonical_id},
                ),
                "link candidate to canonical",
            )
            if linked.get("changed") is not True:
                raise RuntimeError(f"Expected link-canonical to change state: {linked}")

            queue_after = assert_object(
                client.get(
                    "/v1/candidates",
                    params={"project_slug": ctx.project_slug, "status": "open", "q": label},
                ),
                "list open candidates after link",
            )
            queue_after_rows = queue_after.get("candidates")
            if not isinstance(queue_after_rows, list):
                raise RuntimeError(f"Expected candidates list after link: {queue_after}")
            if any(
                isinstance(row, dict) and int(row.get("id", -1)) == candidate_id
                for row in queue_after_rows
            ):
                raise RuntimeError(
                    f"Candidate {candidate_id} still present in open queue after link"
                )

            linked_substrates = assert_object(
                client.get(
                    f"/v1/canonical-locations/{canonical_id}/linked-substrates",
                    params={"project_slug": ctx.project_slug},
                ),
                "linked substrates",
            )

        substrates = linked_substrates.get("substrates")
        if not isinstance(substrates, list) or not any(
            isinstance(row, dict) and int(row.get("id", -1)) == candidate_id for row in substrates
        ):
            raise RuntimeError(
                f"Linked substrates did not include candidate {candidate_id}: {linked_substrates}"
            )

        log("Smoke stylebook editorial passed.")
        log(f"Stylebook: {stylebook_slug!r}")
        log(f"Canonical: {canonical_id}")
        log(f"Candidate: {candidate_id}")
        return 0
    finally:
        if not keep_smoke_data():
            with smoke_db_session() as session:
                if candidate_id:
                    article_ids = {
                        int(row)
                        for row in session.exec(
                            select(SubstrateLocationMention.article_id).where(
                                SubstrateLocationMention.location_id == candidate_id
                            )
                        ).all()
                        if row is not None
                    }
                    delete_smoke_substrate_rows(
                        session,
                        article_ids=article_ids,
                        location_ids={candidate_id},
                    )
                if canonical_id:
                    delete_smoke_canonical(
                        session,
                        canonical_id=canonical_id,
                        allowed_linked_location_ids={candidate_id} if candidate_id else frozenset(),
                    )
                session.commit()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPError as exc:
        print(f"HTTP smoke failure: {http_error_detail(exc)}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"Smoke failure: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
