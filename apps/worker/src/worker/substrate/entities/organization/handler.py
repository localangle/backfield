"""Organization (organizations) persist handler for substrate orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from backfield_db import SubstrateOrganization, SubstrateOrganizationMention
from backfield_entities.canonical.link import CANONICAL_LINK_UNLINKED
from backfield_entities.canonical.plan_types import CanonicalPersistPlan
from backfield_entities.entities.organization.persist import (
    apply_canonical_persist_plan,
    apply_canonical_persist_plan_review_only,
    refresh_aliases_for_linked_organization,
)
from backfield_entities.entities.organization.policy import (
    decide_organization_canonical_persist_plan,
    plan_requires_llm_organization_canonical_adjudication,
    plan_requires_llm_organization_name_variant_recall,
    replan_organization_canonical_after_name_variants,
)
from backfield_entities.entities.organization.review import (
    organization_boundary_recommends_defer_only,
    parse_organization_boundary_from_entry,
    plan_with_boundary_defer_override,
)
from sqlmodel import Session, col, select

from worker.substrate.canonical.parallel_llm import (
    canonical_adjudication_max_concurrent,
    commit_session_before_session_free_llm,
    run_callables_parallel,
)
from worker.substrate.entities.organization.adjudication import (
    OrganizationAdjudicationPrepared,
    llm_suggest_organization_name_variants,
    prepare_organization_adjudication,
    resolve_organization_adjudication_plan,
    run_organization_adjudication_llm,
)
from worker.substrate.entities.organization.mentions import (
    _upsert_mention_and_occurrence,
    dispose_orphan_substrates_after_retired_mentions,
    retire_stale_article_mentions_for_rerun,
)
from worker.substrate.entities.organization.upsert import (
    _iter_organizations_entries,
    _upsert_organization,
)
from worker.substrate.entities.registry import (
    DomainReconciliationSummary,
    HandlerPersistResult,
    PersistContext,
    register_persist_handler,
)

logger = logging.getLogger(__name__)


@dataclass
class _OrgCanonicalWork:
    organization: SubstrateOrganization
    bucket: str
    entry: dict[str, Any]
    plan: CanonicalPersistPlan


@dataclass
class _PendingOrgAdjudication(_OrgCanonicalWork):
    prepared: OrganizationAdjudicationPrepared


def _active_mention_for_article_organization(
    session: Session,
    *,
    article_id: int,
    organization_id: int,
) -> Any | None:
    return session.exec(
        select(SubstrateOrganizationMention).where(
            SubstrateOrganizationMention.article_id == int(article_id),
            SubstrateOrganizationMention.organization_id == int(organization_id),
            col(SubstrateOrganizationMention.deleted).is_(False),
        )
    ).first()


def _editor_touched_mention(mention: Any | None) -> bool:
    return bool(mention is not None and (bool(mention.edited) or bool(mention.added)))


def _apply_organization_plan_and_mention(
    session: Session,
    ctx: PersistContext,
    *,
    organization: SubstrateOrganization,
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
            organization=organization,
            plan=plan,
            organizations_bucket=bucket,
            provenance="substrate_ingest",
            auto_apply_canonicalization=True,
        )
    else:
        apply_canonical_persist_plan_review_only(
            session,
            stylebook_id=ctx.stylebook_id,
            organization=organization,
            plan=plan,
            organizations_bucket=bucket,
        )
    _upsert_mention_and_occurrence(
        session,
        article_id=int(ctx.article_id),
        organization_id=int(organization.id),  # type: ignore[arg-type]
        article_text=ctx.article_text,
        entry=entry,
        run_id=ctx.run_id,
        graph_id=ctx.graph_id,
        bucket=bucket,
        preserve_editor_changes=ctx.policy == "smart_merge",
    )


def _queue_adjudication_or_apply(
    session: Session,
    ctx: PersistContext,
    *,
    work: _OrgCanonicalWork,
    pending_adjudication: list[_PendingOrgAdjudication],
    adj_model: str,
) -> None:
    organization = work.organization
    plan = work.plan
    if plan_requires_llm_organization_canonical_adjudication(plan, organization):
        prepared = prepare_organization_adjudication(
            session,
            plan=plan,
            organization=organization,
            stylebook_id=int(ctx.stylebook_id),  # type: ignore[arg-type]
            model=adj_model,
            model_config_id=ctx.settings.adjudication_ai_model_config_id,
        )
        if prepared is not None:
            pending_adjudication.append(
                _PendingOrgAdjudication(
                    organization=organization,
                    bucket=work.bucket,
                    entry=work.entry,
                    plan=plan,
                    prepared=prepared,
                )
            )
            return
    _apply_organization_plan_and_mention(
        session,
        ctx,
        organization=organization,
        bucket=work.bucket,
        entry=work.entry,
        plan=plan,
    )


class OrganizationPersistHandler:
    consolidated_key = "organizations"

    def persist(self, session: Session, ctx: PersistContext) -> HandlerPersistResult:
        organizations = ctx.consolidated.get("organizations")
        if not isinstance(organizations, list):
            raise RuntimeError(
                "Organization persist handler requires consolidated['organizations'] as an array"
            )

        policy = ctx.policy
        if not organizations and policy != "replace":
            return HandlerPersistResult(
                summary=DomainReconciliationSummary(policy=policy, domain="organizations"),
                retired_mentions=0,
                disposed_substrates=0,
            )

        touched_organization_ids: set[int] = set()
        added = 0
        updated = 0
        skipped = 0
        preserved = 0
        pending_variant_recall: list[_OrgCanonicalWork] = []
        pending_adjudication: list[_PendingOrgAdjudication] = []
        adj_model = (ctx.settings.adjudication_model or "").strip() or "gpt-5-nano"
        ai_assisted = ctx.settings.canonicalization_mode == "ai_assisted"

        for idx, (bucket, entry) in enumerate(_iter_organizations_entries(organizations)):
            anchor = entry.get("id") or entry.get("mention_id")
            if not (isinstance(anchor, str) and str(anchor).strip()):
                anchor = f"stylebook_output:{idx}"
                entry["id"] = anchor
            upserted = _upsert_organization(
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
            organization = upserted.organization
            active_mention = _active_mention_for_article_organization(
                session,
                article_id=int(ctx.article_id),
                organization_id=int(organization.id),  # type: ignore[arg-type]
            )
            if policy == "add_only" and active_mention is not None:
                skipped += 1
                touched_organization_ids.add(int(organization.id))  # type: ignore[arg-type]
                continue
            if policy == "smart_merge" and _editor_touched_mention(active_mention):
                preserved += 1
                touched_organization_ids.add(int(organization.id))  # type: ignore[arg-type]
                continue
            if active_mention is None or upserted.created:
                added += 1
            elif upserted.updated:
                updated += 1
            if organization.id is not None:
                touched_organization_ids.add(int(organization.id))
            if (
                ctx.stylebook_id is not None
                and organization.stylebook_organization_canonical_id is not None
            ):
                refresh_aliases_for_linked_organization(
                    session,
                    stylebook_id=ctx.stylebook_id,
                    organization=organization,
                    provenance="substrate_ingest",
                )
                _upsert_mention_and_occurrence(
                    session,
                    article_id=int(ctx.article_id),
                    organization_id=int(organization.id),  # type: ignore[arg-type]
                    article_text=ctx.article_text,
                    entry=entry,
                    run_id=ctx.run_id,
                    graph_id=ctx.graph_id,
                    bucket=bucket,
                    preserve_editor_changes=policy == "smart_merge",
                )
            elif ctx.stylebook_id is not None:
                plan = decide_organization_canonical_persist_plan(
                    session,
                    stylebook_id=ctx.stylebook_id,
                    organization=organization,
                    organizations_bucket=bucket,
                    auto_apply_canonicalization=ctx.settings.auto_apply_canonicalization,
                )
                boundary = parse_organization_boundary_from_entry(entry)
                if boundary is not None and organization_boundary_recommends_defer_only(boundary):
                    plan = plan_with_boundary_defer_override(plan, boundary=boundary)
                    apply_canonical_persist_plan_review_only(
                        session,
                        stylebook_id=ctx.stylebook_id,
                        organization=organization,
                        plan=plan,
                        organizations_bucket=bucket,
                    )
                    _upsert_mention_and_occurrence(
                        session,
                        article_id=int(ctx.article_id),
                        organization_id=int(organization.id),  # type: ignore[arg-type]
                        article_text=ctx.article_text,
                        entry=entry,
                        run_id=ctx.run_id,
                        graph_id=ctx.graph_id,
                        bucket=bucket,
                        preserve_editor_changes=policy == "smart_merge",
                    )
                elif (
                    ai_assisted
                    and plan_requires_llm_organization_name_variant_recall(plan, organization)
                ):
                    pending_variant_recall.append(
                        _OrgCanonicalWork(
                            organization=organization,
                            bucket=bucket,
                            entry=entry,
                            plan=plan,
                        )
                    )
                elif ai_assisted and plan_requires_llm_organization_canonical_adjudication(
                    plan, organization
                ):
                    prepared = prepare_organization_adjudication(
                        session,
                        plan=plan,
                        organization=organization,
                        stylebook_id=ctx.stylebook_id,
                        model=adj_model,
                        model_config_id=ctx.settings.adjudication_ai_model_config_id,
                    )
                    if prepared is not None:
                        pending_adjudication.append(
                            _PendingOrgAdjudication(
                                organization=organization,
                                bucket=bucket,
                                entry=entry,
                                plan=plan,
                                prepared=prepared,
                            )
                        )
                    else:
                        _apply_organization_plan_and_mention(
                            session,
                            ctx,
                            organization=organization,
                            bucket=bucket,
                            entry=entry,
                            plan=plan,
                        )
                else:
                    _apply_organization_plan_and_mention(
                        session,
                        ctx,
                        organization=organization,
                        bucket=bucket,
                        entry=entry,
                        plan=plan,
                    )
            elif organization.stylebook_organization_canonical_id is None:
                organization.canonical_link_status = CANONICAL_LINK_UNLINKED
                session.add(organization)
                _upsert_mention_and_occurrence(
                    session,
                    article_id=int(ctx.article_id),
                    organization_id=int(organization.id),  # type: ignore[arg-type]
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
                    organization_id=int(organization.id),  # type: ignore[arg-type]
                    article_text=ctx.article_text,
                    entry=entry,
                    run_id=ctx.run_id,
                    graph_id=ctx.graph_id,
                    bucket=bucket,
                    preserve_editor_changes=policy == "smart_merge",
                )

        if pending_variant_recall and ai_assisted:
            variant_specs = [
                (
                    item,
                    str(item.organization.name),
                    str(item.organization.normalized_name),
                    item.organization.organization_type,
                    int(item.organization.id),  # type: ignore[arg-type]
                )
                for item in pending_variant_recall
            ]
            commit_session_before_session_free_llm(session)
            max_workers = canonical_adjudication_max_concurrent()
            variant_results = run_callables_parallel(
                [
                    lambda spec=spec: llm_suggest_organization_name_variants(
                        name=spec[1],
                        normalized_name=spec[2],
                        organization_type=spec[3],
                        model=adj_model,
                        model_config_id=ctx.settings.adjudication_ai_model_config_id,
                    )
                    for spec in variant_specs
                ],
                max_workers=max_workers,
            )
            for spec, variants in zip(variant_specs, variant_results, strict=True):
                item = spec[0]
                organization_id = spec[4]
                organization = session.get(SubstrateOrganization, organization_id)
                if organization is None:
                    logger.warning(
                        "substrate_organization id=%s missing after variant recall LLM; skipping",
                        organization_id,
                    )
                    continue
                plan = item.plan
                if variants:
                    plan = replan_organization_canonical_after_name_variants(
                        session,
                        stylebook_id=int(ctx.stylebook_id),  # type: ignore[arg-type]
                        organization=organization,
                        variant_names=variants,
                        organizations_bucket=item.bucket,
                        auto_apply_canonicalization=ctx.settings.auto_apply_canonicalization,
                    )
                if ai_assisted:
                    _queue_adjudication_or_apply(
                        session,
                        ctx,
                        work=_OrgCanonicalWork(
                            organization=organization,
                            bucket=item.bucket,
                            entry=item.entry,
                            plan=plan,
                        ),
                        pending_adjudication=pending_adjudication,
                        adj_model=adj_model,
                    )
                else:
                    _apply_organization_plan_and_mention(
                        session,
                        ctx,
                        organization=organization,
                        bucket=item.bucket,
                        entry=item.entry,
                        plan=plan,
                    )

        if pending_adjudication:
            commit_session_before_session_free_llm(session)
            max_workers = canonical_adjudication_max_concurrent()
            llm_results = run_callables_parallel(
                [
                    lambda p=item.prepared: run_organization_adjudication_llm(p)
                    for item in pending_adjudication
                ],
                max_workers=max_workers,
            )
            for item, llm_data in zip(pending_adjudication, llm_results, strict=True):
                organization_id = int(item.organization.id)  # type: ignore[arg-type]
                organization = session.get(SubstrateOrganization, organization_id)
                if organization is None:
                    logger.warning(
                        "substrate_organization id=%s missing after adjudication LLM; "
                        "skipping apply",
                        organization_id,
                    )
                    continue
                plan = resolve_organization_adjudication_plan(
                    item.plan,
                    prepared=item.prepared,
                    llm_data=llm_data,
                    session=session,
                    stylebook_id=int(ctx.stylebook_id),
                )
                _apply_organization_plan_and_mention(
                    session,
                    ctx,
                    organization=organization,
                    bucket=item.bucket,
                    entry=item.entry,
                    plan=plan,
                )

        retired_mentions = 0
        substrates_disposed = 0
        should_retire_stale = policy == "replace" or (
            policy == "smart_merge" and bool(touched_organization_ids)
        )
        if should_retire_stale:
            retired_mentions, retired_organization_ids, retirement_preserved = (
                retire_stale_article_mentions_for_rerun(
                    session,
                    article_id=int(ctx.article_id),
                    touched_organization_ids=touched_organization_ids,
                )
            )
            preserved += retirement_preserved
            if retired_organization_ids:
                substrates_disposed = dispose_orphan_substrates_after_retired_mentions(
                    session,
                    project_id=int(ctx.project_id),
                    organization_ids=retired_organization_ids,
                )
            if retired_mentions or substrates_disposed:
                logger.warning(
                    "Superseded organizations ingest for article_id=%s run_id=%s: %s mention(s) "
                    "retired, %s orphan substrate(s) disposed",
                    ctx.article_id,
                    ctx.run_id,
                    retired_mentions,
                    substrates_disposed,
                )

        return HandlerPersistResult(
            summary=DomainReconciliationSummary(
                policy=policy,
                domain="organizations",
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


register_persist_handler(OrganizationPersistHandler())
