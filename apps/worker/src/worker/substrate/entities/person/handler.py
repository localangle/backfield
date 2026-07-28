"""Person (people) persist handler for substrate orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backfield_db import SubstratePerson, SubstratePersonMention
from backfield_entities.canonical.link import CANONICAL_LINK_PENDING, CANONICAL_LINK_UNLINKED
from backfield_entities.canonical.link_commit_gate import sync_link_commit_blocked
from backfield_entities.canonical.plan_types import CanonicalPersistPlan
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

from worker.substrate.canonical.parallel_llm import (
    canonical_adjudication_max_concurrent,
    commit_session_before_session_free_llm,
    run_callables_parallel,
)
from worker.substrate.entities.person.adjudication import (
    PersonAdjudicationPrepared,
    prepare_person_adjudication,
    resolve_person_adjudication_plan,
    run_person_adjudication_llm,
)
from worker.substrate.entities.person.mentions import (
    _mention_texts_from_entry,
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


@dataclass
class _PendingPersonAdjudication:
    person: SubstratePerson
    bucket: str
    entry: dict[str, Any]
    plan: CanonicalPersistPlan
    prepared: PersonAdjudicationPrepared


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


def _apply_person_plan_and_mention(
    session: Session,
    ctx: PersistContext,
    *,
    person: SubstratePerson,
    bucket: str,
    entry: dict[str, Any],
    plan: CanonicalPersistPlan,
) -> None:
    if ctx.stylebook_id is None:
        return
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
    _upsert_mention_and_occurrence(
        session,
        article_id=int(ctx.article_id),
        person_id=int(person.id),  # type: ignore[arg-type]
        article_text=ctx.article_text,
        entry=entry,
        run_id=ctx.run_id,
        graph_id=ctx.graph_id,
        bucket=bucket,
        preserve_editor_changes=ctx.policy == "smart_merge",
    )


class PersonPersistHandler:
    consolidated_key = "people"

    def persist(self, session: Session, ctx: PersistContext) -> HandlerPersistResult:
        people = ctx.consolidated.get("people")
        if not isinstance(people, list):
            raise RuntimeError(
                "Person persist handler requires consolidated['people'] as an array"
            )

        policy = ctx.policy
        if not people and policy != "replace":
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
        pending_adjudication: list[_PendingPersonAdjudication] = []
        adj_model = (ctx.settings.adjudication_model or "").strip() or "gpt-5-nano"
        ai_assisted = ctx.settings.canonicalization_mode == "ai_assisted"

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
                veto = sync_link_commit_blocked(
                    session,
                    entity_type="person",
                    substrate_row=person,
                    canonical_id=str(person.stylebook_person_canonical_id),
                    stylebook_id=ctx.stylebook_id,
                )
                if veto is None:
                    refresh_aliases_for_linked_person(
                        session,
                        stylebook_id=ctx.stylebook_id,
                        person=person,
                        provenance="substrate_ingest",
                    )
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
                    continue
                logger.warning(
                    "Linked person id=%s fails commit gate (%s); clearing FK and re-planning",
                    person.id,
                    veto,
                )
                person.stylebook_person_canonical_id = None
                person.canonical_link_status = CANONICAL_LINK_PENDING
                session.add(person)
            if ctx.stylebook_id is not None and person.stylebook_person_canonical_id is None:
                plan = decide_person_canonical_persist_plan(
                    session,
                    stylebook_id=ctx.stylebook_id,
                    person=person,
                    people_bucket=bucket,
                    auto_apply_canonicalization=ctx.settings.auto_apply_canonicalization,
                )
                needs_llm = (
                    ai_assisted
                    and plan_requires_llm_person_canonical_adjudication(plan, person)
                )
                if needs_llm:
                    prepared = prepare_person_adjudication(
                        session,
                        plan=plan,
                        person=person,
                        stylebook_id=ctx.stylebook_id,
                        model=adj_model,
                        model_config_id=ctx.settings.adjudication_ai_model_config_id,
                        article_text=ctx.article_text,
                        mention_texts=_mention_texts_from_entry(entry),
                    )
                    if prepared is not None:
                        pending_adjudication.append(
                            _PendingPersonAdjudication(
                                person=person,
                                bucket=bucket,
                                entry=entry,
                                plan=plan,
                                prepared=prepared,
                            )
                        )
                        continue
                _apply_person_plan_and_mention(
                    session,
                    ctx,
                    person=person,
                    bucket=bucket,
                    entry=entry,
                    plan=plan,
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
            else:
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

        if pending_adjudication:
            commit_session_before_session_free_llm(session)
            max_workers = canonical_adjudication_max_concurrent()
            llm_tasks = [
                lambda p=item.prepared: run_person_adjudication_llm(p)
                for item in pending_adjudication
            ]
            llm_results = run_callables_parallel(llm_tasks, max_workers=max_workers)
            for item, llm_data in zip(pending_adjudication, llm_results, strict=True):
                person_id = int(item.person.id)  # type: ignore[arg-type]
                person = session.get(SubstratePerson, person_id)
                if person is None:
                    logger.warning(
                        "substrate_person id=%s missing after adjudication LLM; skipping apply",
                        person_id,
                    )
                    continue
                plan = resolve_person_adjudication_plan(
                    item.plan,
                    prepared=item.prepared,
                    llm_data=llm_data,
                    session=session,
                    stylebook_id=int(ctx.stylebook_id),
                )
                _apply_person_plan_and_mention(
                    session,
                    ctx,
                    person=person,
                    bucket=item.bucket,
                    entry=item.entry,
                    plan=plan,
                )

        retired_mentions = 0
        substrates_disposed = 0
        should_retire_stale = policy == "replace" or (
            policy == "smart_merge" and bool(touched_person_ids)
        )
        if should_retire_stale:
            retired_mentions, retired_person_ids, retirement_preserved = (
                retire_stale_article_mentions_for_rerun(
                    session,
                    article_id=int(ctx.article_id),
                    touched_person_ids=touched_person_ids,
                )
            )
            preserved += retirement_preserved
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
