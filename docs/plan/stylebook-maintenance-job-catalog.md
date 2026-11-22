# Stylebook maintenance job catalog

**Status:** Planning only; nothing here is a runtime contract.

This catalog decomposes the work learned from the place and person cleanup passes into discrete
capabilities. It is the proposed boundary map for future functions, APIs, pipeline jobs, and
operator-facing agent skills. It complements the requirements and evidence in
[`stylebook-maintenance-program.md`](stylebook-maintenance-program.md),
[`stylebook-places-requirements.md`](stylebook-places-requirements.md), and
[`stylebook-people-requirements.md`](stylebook-people-requirements.md).

## Job contract

Keep assessment, decision, mutation, and verification separate:

1. **Read jobs** produce immutable evidence.
2. **Decision jobs** consume evidence and produce typed plans.
3. **Apply jobs** consume plans with current-state preconditions.
4. **Verification jobs** independently inspect the result.

No assessment job should mutate data as a side effect.

## Packaging guidance

- Use a **skill** when the job interviews an operator, coordinates several capabilities, or produces
  a review artifact.
- Use a **function or API capability** for deterministic queries, guards, and mutations with a
  narrow typed contract.
- Use a **pipeline job** for fan-out model work, bounded iteration, or batch processing with
  resumable progress.

## Foundation

| Job | Description | Produces | Best shape |
| --- | --- | --- | --- |
| Define the category identity contract | State what counts as one durable canonical, what stays separate, and what is not an entity. Include positive and negative examples before any finder or model runs. | Versioned category contract and examples | Skill |
| Collect scope and autonomy policy | Interview for home region, minimum evidence, sensitive classes, allowed actions, confidence policy, run caps, and which decisions require approval. | Validated run policy | Skill |
| Resolve run target | Resolve organization, Stylebook, project, category, environment, and time cohort explicitly. Refuse ambiguous or missing targets. | Immutable run context | Function/API |
| Acquire maintenance lease | Prevent overlapping cleanup or ingest writes for the same scope, or record the allowed concurrency model when a full freeze is unnecessary. | Lease or conflict report | Function/API |
| Establish cohort and watermark | Select records created or changed in the requested period while retaining cross-cohort canonicals as possible match targets. | Stable workset and watermark | Function/API |
| Inventory catalog and queues | Count canonicals, linked evidence, pending and waived candidates, check results, zero-evidence records, and unread cohorts by type. | Baseline metrics snapshot | Function/API |
| Diagnose queue provenance | Explain why each cohort exists: ingest race, gate veto, finder blind spot, missing scope rule, bad reference data, or a previous cleanup side effect. | Cause-coded queue inventory | Pipeline job |
| Validate reference data | Check any data used as a referee before trusting it, such as state polygons, country names, trusted aliases, or taxonomy values. | Reference health report and exclusions | Function/API |

## Discovery and decision

| Job | Description | Produces | Best shape |
| --- | --- | --- | --- |
| Generate duplicate candidates | Build high-recall pair or cluster candidates from normalized labels, aliases, type-aware keys, and category-specific blocking rules. | Versioned candidate edges or clusters | Function/API |
| Probe finder blind spots | Search outside the current finder for cases a person would notice: spacing, punctuation, nicknames, dropped words, one-letter slips, translations, or trusted aliases. | Missed-match sample and proposed blocking keys | Pipeline job |
| Recall canonical match candidates | For each substrate candidate, retrieve and rank a small set of existing canonicals using names, aliases, titles, affiliations, addresses, and geometry. | Ranked canonical candidates with scores | Function/API |
| Apply deterministic triage | Run safe fold, link, waive, dismiss, and hard-conflict rules before model review. Every rule emits a reason and the evidence it used. | Rule decisions and unresolved remainder | Function/API |
| Build evidence packets | Assemble immutable, hashed packets containing profiles, aliases, article excerpts, counts, relationships, candidate records, and policy context. Mark article text as untrusted. | Typed evidence packets with hashes | Function/API |
| Enrich with an external referee | Ask an outside source only where it can discriminate between hypotheses. It may support either side or return unresolved; it never decides alone. | Referee evidence and acceptance checks | Pipeline job |
| Run independent readers | Fan evidence packets to independent models using a versioned category rubric and structured verdict schema. | Per-reader verdicts, confidence, and reasons | Pipeline job |
| Reconcile reader verdicts | Apply consensus policy to verdict, target, type, label, and confidence. Preserve disagreement rather than forcing a decision. | Consensus, disagreement, or hold | Function/API |
| Apply policy gates and vetoes | Evaluate deterministic safety constraints after readers: incompatible numbers, jurisdictions, suffixes, organizations, sensitive classes, or component conflicts. | Guarded decisions with veto reasons | Function/API |
| Adversarially audit high-impact actions | Give merges, retirements, geometry replacements, and other high-impact decisions a fresh challenge focused on the strongest counter-evidence. | Approved, downgraded, or blocked action | Pipeline job |
| Build a component-safe mutation plan | Collapse pair decisions into non-conflicting components, select survivors, order dependent operations, and prevent a record from being both retained and deleted. | Ordered operation plan | Function/API |
| Produce hold and approval lists | Separate unresolved, sensitive, policy-blocked, and owner-approval items into named lists with reasons and enough evidence to act later. | Reviewable residual lists | Skill |

## Places

| Job | Description | Produces | Best shape |
| --- | --- | --- | --- |
| Normalize place identity | Normalize accents, apostrophes, translations, word order, renamed venues, numbered labels, and address-like labels without erasing meaningful geography. | Place match keys and variant reasons | Function/API |
| Validate place type and label | Distinguish city, region, neighborhood, natural feature, venue, chain branch, address, intersection, span, and area-versus-point expectations. | Canonical label/type assessment | Function/API |
| Audit geometry representation | Check that JSON and PostGIS geometry agree, area entities are not stored as points, and searchable geometry is present when expected. | Geometry storage defects | Function/API |
| Audit geographic consistency | Test containment, label-versus-address consistency, distance to area edge, linked-mention agreement, and reference-shape validity. | Cause-coded geography findings | Function/API |
| Adjudicate duplicate places | Decide same place, related-but-distinct, multi-site ambiguity, or different place using name, type, address, geometry, aliases, and mention evidence. | Place duplicate verdict | Pipeline job |
| Adjudicate location candidates | Choose link, create, waive, or hold using scope policy, ranked catalog candidates, validated geocoding, and agreed label, type, and shape. | Location candidate action | Pipeline job |
| Repair place mismatches | Separate trusted rename aliases from wrong links, then relink, preserve an alias, or route a geographic disagreement to geometry repair. | Mismatch repair plan | Function/API |
| Plan geometry correction | Choose a validated replacement shape, clear a clearly wrong shape, or keep the canonical and refresh incorrect linked mentions. Record source and attribution. | Geometry mutation with provenance | Pipeline job |

## People

| Job | Description | Produces | Best shape |
| --- | --- | --- | --- |
| Normalize person name variants | Generate typed variants for nicknames, initials, middle names, compound surnames, punctuation, spacing, transliteration, and one-letter slips without treating each as identity proof. | Person blocking keys and variant kind | Function/API |
| Disambiguate same-name people | Use title, affiliation, standing type, article context, dates, and relationships to distinguish real duplicates from unrelated people with identical labels. | Same-person, different-person, or hold | Pipeline job |
| Adjudicate single-token people | Separate legitimate mononyms and stage names from surname-only, first-name-only, username, relational-role, and mixed-identity records. | Keep, complete, merge, retire, or hold | Pipeline job |
| Detect non-people in the person catalog | Identify bands, organizations, animals, fictional characters, works, and generic roles even when no matching non-person canonical exists. | Non-person retirement proposal | Pipeline job |
| Detect mixed or corrupted identity evidence | Flag one substrate that combines unrelated people, word senses, article typos, or extraction errors so it is retired or repaired rather than merged wholesale. | Contamination finding and safe disposition | Pipeline job |
| Resolve standing person metadata | Choose the durable person type, title, affiliation, public-figure state, and primary evidence while keeping story-specific roles on mentions. | Resolved survivor metadata | Function/API |
| Adjudicate person candidates | Choose link, create, waive, or hold using ranked canonicals, relationship context, stage-name rules, mention count, public status, and reader agreement. | Person candidate action | Pipeline job |
| Enforce sensitive-person workflow | Apply the stricter read, approval, privacy, and mutation policy for crime/justice subjects and other configured sensitive classes. | Dismissal, approval proposal, or protected hold | Function/API |

## Apply and assurance

| Job | Description | Produces | Best shape |
| --- | --- | --- | --- |
| Preflight freshness and drift | Re-read every source, target, evidence hash, link state, and policy version immediately before mutation. Quarantine stale items and abort on unexplained global drift. | Executable and quarantined operation sets | Function/API |
| Capture before-state and recovery data | Record the complete affected state before changing it: profiles, aliases, links, relationships, geometry, dismissals, and metadata. A backup checkpoint may be added by policy. | Durable ledger and recovery checkpoint | Function/API |
| Simulate the mutation plan | Execute the real shared mutation functions inside rollback-only transactions and verify expected deltas, preservation, and survivor metadata. | Dry-run report with per-item failures | Pipeline job |
| Apply canonical merges | Merge through the shared entity library, preserving aliases, metadata, relationships, evidence, provenance, and category-specific fields. | Committed merge result | Function/API |
| Apply candidate decisions | Create, link, waive, or hold through shared persistence functions with reason codes, idempotency, and current-state preconditions. | Committed candidate disposition | Function/API |
| Apply repairs and retirements | Update labels, types, geometry, aliases, or links; retire invalid canonicals without deleting underlying mentions; record every action's provenance. | Committed repair or retirement | Function/API |
| Reindex affected entities | Queue semantic and search reindexing for moved or changed substrates, canonicals, and affected articles as part of the mutation transaction. | Reindex work records | Function/API |
| Verify integrity and preservation | Independently check dangling links, invalid states, evidence counts, relationships, alias trust, geometry consistency, and records left on deleted canonicals. | Signed post-apply integrity report | Function/API |
| Refresh checks and run closure | Refresh all affected queues, measure cleanup-created side effects, and repeat only within a bounded iteration cap until no actionable residual remains. | Closure status and residual workset | Pipeline job |
| Audit an outcome sample | Blindly sample merges, dismissals, links, creates, waives, and repairs by tier to estimate error rates and calibrate future autonomy. | Labeled audit set and quality metrics | Skill |
| Publish run report and lessons | Report before/after counts, decisions by tier, costs, errors, residuals, review lists, integrity results, and requirements that should change. | Durable run report and spec deltas | Skill |
| Undo or reopen a decision | Restore a merge or repair from its ledger, or reopen a dismissal or waive when evidence, finder version, or policy has changed. | Reversal result and new audit event | Function/API |
