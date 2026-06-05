"""Person (people) persist handler for substrate orchestration."""

from __future__ import annotations

import logging
from typing import Any

from backfield_db import SubstratePersonMention
from backfield_entities.canonical.link import CANONICAL_LINK_UNLINKED
from backfield_entities.entities.person.persist import (
    apply_canonical_persist_plan,
    apply_canonical_persist_plan_review_only,
    refresh_aliases_for_linked_person,
)
from backfield_entities.entities.person.policy import (
    decide_person_canonical_persist_plan,
    plan_requires_llm_person_canonical_adjudication,
)
from sqlmodel import Session, col, select

from worker.substrate.entities.person.adjudication import adjudicate_ambiguous_person_plan_with_llm
from worker.substrate.entities.person.mentions import (
    _upsert_mention_and_occurrence,
    dispose_orphan_substrates_after_retired_mentions,
    retire_stale_article_mentions_for_rerun,
)
from worker.substrate.entities.person.upsert import _iter_people_entries, _upsert_person
from worker.substrate.entities.registry import (
    DomainReconciliationSummary,
    HandlerPersistResult,
    PersistContext,
    register_persist_handler,
)

logger = logging.getLogger(__name__)


def _active_mention_for_article_person(
    session: Session,
    *,
    article_id: int,
    person_id: int,
) -> Any | None:
    return session.exec(
        select(SubstratePersonMention).where(
            SubstratePersonMention.article_id == int(article_id),
            SubstratePersonMention.person_id == int(person_id),
            col(SubstratePersonMention.deleted).is_(False),
        )
    ).first()


def _editor_touched_mention(mention: Any | None) -> bool:
    return bool(mention is not None and (bool(mention.edited) or bool(mention.added)))


class PersonPersistHandler:
    consolidated_key = "people"

    def persist(self, session: Session, ctx: PersistContext) -> HandlerPersistResult:
        people = ctx.consolidated.get("people")
        if not isinstance(people, list):
            raise RuntimeError(
                "Person persist handler requires consolidated['people'] as an array"
            )

        policy = ctx.policy
        if not people:
            return HandlerPersistResult(
                summary=DomainReconciliationSummary(policy=policy, domain="people"),
                retired_mentions=0,
                disposed_substrates=0,
            )

        touched_person_ids: set[int] = set()
        added = 0
        updated = 0
        skipped = 0
        preserved = 0

        for idx, (bucket, entry) in enumerate(_iter_people_entries(people)):
            anchor = entry.get("id") or entry.get("mention_id")
            if not (isinstance(anchor, str) and str(anchor).strip()):
                anchor = f"stylebook_output:{idx}"
                entry["id"] = anchor
            upserted = _upsert_person(
                session,
                project_id=ctx.project_id,
                bucket=bucket,
                entry=entry,
                run_id=ctx.run_id,
                graph_id=ctx.graph_id,
                update_existing=policy != "add_only",
            )
            if upserted is None:
                continue
            person = upserted.person
            active_mention = _active_mention_for_article_person(
                session,
                article_id=int(ctx.article_id),
                person_id=int(person.id),  # type: ignore[arg-type]
            )
            if policy == "add_only" and active_mention is not None:
                skipped += 1
                touched_person_ids.add(int(person.id))  # type: ignore[arg-type]
                continue
            if policy == "smart_merge" and _editor_touched_mention(active_mention):
                preserved += 1
                touched_person_ids.add(int(person.id))  # type: ignore[arg-type]
                continue
            if active_mention is None or upserted.created:
                added += 1
            elif upserted.updated:
                updated += 1
            if person.id is not None:
                touched_person_ids.add(int(person.id))
            if ctx.stylebook_id is not None and person.stylebook_person_canonical_id is not None:
                refresh_aliases_for_linked_person(
                    session,
                    stylebook_id=ctx.stylebook_id,
                    person=person,
                    provenance="substrate_ingest",
                )
            elif ctx.stylebook_id is not None:
                plan = decide_person_canonical_persist_plan(
                    session,
                    stylebook_id=ctx.stylebook_id,
                    person=person,
                    people_bucket=bucket,
                    auto_apply_canonicalization=ctx.settings.auto_apply_canonicalization,
                )
                if (
                    ctx.settings.canonicalization_mode == "ai_assisted"
                    and plan_requires_llm_person_canonical_adjudication(plan, person)
                ):
                    adj_model = (ctx.settings.adjudication_model or "").strip() or "gpt-5-nano"
                    plan = adjudicate_ambiguous_person_plan_with_llm(
                        session,
                        plan=plan,
                        person=person,
                        stylebook_id=ctx.stylebook_id,
                        model=adj_model,
                        model_config_id=ctx.settings.adjudication_ai_model_config_id,
                    )
                if ctx.settings.auto_apply_canonicalization:
                    apply_canonical_persist_plan(
                        session,
                        stylebook_id=ctx.stylebook_id,
                        person=person,
                        plan=plan,
                        people_bucket=bucket,
                        provenance="substrate_ingest",
                        auto_apply_canonicalization=True,
                    )
                else:
                    apply_canonical_persist_plan_review_only(
                        session,
                        stylebook_id=ctx.stylebook_id,
                        person=person,
                        plan=plan,
                        people_bucket=bucket,
                    )
            elif person.stylebook_person_canonical_id is None:
                person.canonical_link_status = CANONICAL_LINK_UNLINKED
                session.add(person)
            _upsert_mention_and_occurrence(
                session,
                article_id=int(ctx.article_id),
                person_id=int(person.id),  # type: ignore[arg-type]
                article_text=ctx.article_text,
                entry=entry,
                run_id=ctx.run_id,
                graph_id=ctx.graph_id,
                bucket=bucket,
                preserve_editor_changes=policy == "smart_merge",
            )

        retired_mentions = 0
        substrates_disposed = 0
        if policy == "smart_merge" and touched_person_ids:
            retired_mentions, retired_person_ids = retire_stale_article_mentions_for_rerun(
                session,
                article_id=int(ctx.article_id),
                touched_person_ids=touched_person_ids,
            )
            if retired_person_ids:
                substrates_disposed = dispose_orphan_substrates_after_retired_mentions(
                    session,
                    project_id=int(ctx.project_id),
                    person_ids=retired_person_ids,
                )
            if retired_mentions or substrates_disposed:
                logger.warning(
                    "Superseded people ingest for article_id=%s run_id=%s: %s mention(s) retired, "
                    "%s orphan substrate(s) disposed",
                    ctx.article_id,
                    ctx.run_id,
                    retired_mentions,
                    substrates_disposed,
                )

        return HandlerPersistResult(
            summary=DomainReconciliationSummary(
                policy=policy,
                domain="people",
                added=added,
                updated=updated,
                skipped=skipped,
                removed=retired_mentions,
                preserved=preserved,
                disposed=substrates_disposed,
            ),
            retired_mentions=retired_mentions,
            disposed_substrates=substrates_disposed,
        )


register_persist_handler(PersonPersistHandler())
