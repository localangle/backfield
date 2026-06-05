"""Organization (organizations) persist handler for substrate orchestration."""

from __future__ import annotations

import logging
from typing import Any

from backfield_db import SubstrateOrganizationMention
from backfield_entities.canonical.link import CANONICAL_LINK_UNLINKED
from backfield_entities.entities.organization.persist import (
    apply_canonical_persist_plan,
    apply_canonical_persist_plan_review_only,
    refresh_aliases_for_linked_organization,
)
from backfield_entities.entities.organization.policy import (
    decide_organization_canonical_persist_plan,
    plan_requires_llm_organization_canonical_adjudication,
)
from sqlmodel import Session, col, select

from worker.substrate.entities.organization.adjudication import (
    adjudicate_ambiguous_organization_plan_with_llm,
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


class OrganizationPersistHandler:
    consolidated_key = "organizations"

    def persist(self, session: Session, ctx: PersistContext) -> HandlerPersistResult:
        organizations = ctx.consolidated.get("organizations")
        if not isinstance(organizations, list):
            raise RuntimeError(
                "Organization persist handler requires consolidated['organizations'] as an array"
            )

        policy = ctx.policy
        if not organizations:
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
            elif ctx.stylebook_id is not None:
                plan = decide_organization_canonical_persist_plan(
                    session,
                    stylebook_id=ctx.stylebook_id,
                    organization=organization,
                    organizations_bucket=bucket,
                    auto_apply_canonicalization=ctx.settings.auto_apply_canonicalization,
                )
                if (
                    ctx.settings.canonicalization_mode == "ai_assisted"
                    and plan_requires_llm_organization_canonical_adjudication(
                        plan, organization
                    )
                ):
                    adj_model = (ctx.settings.adjudication_model or "").strip() or "gpt-5-nano"
                    plan = adjudicate_ambiguous_organization_plan_with_llm(
                        session,
                        plan=plan,
                        organization=organization,
                        stylebook_id=ctx.stylebook_id,
                        model=adj_model,
                        model_config_id=ctx.settings.adjudication_ai_model_config_id,
                    )
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

        retired_mentions = 0
        substrates_disposed = 0
        if policy == "smart_merge" and touched_organization_ids:
            retired_mentions, retired_organization_ids = retire_stale_article_mentions_for_rerun(
                session,
                article_id=int(ctx.article_id),
                touched_organization_ids=touched_organization_ids,
            )
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
