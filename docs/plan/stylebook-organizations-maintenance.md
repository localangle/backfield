# Stylebook maintenance: organizations (running plan)

**Status:** Closed 2026-11-18; nothing here is a runtime contract. Organizations follow places and
people in [`stylebook-maintenance-program.md`](stylebook-maintenance-program.md). The reusable method and
requirements are in [`stylebook-places-requirements.md`](stylebook-places-requirements.md) and
[`stylebook-people-requirements.md`](stylebook-people-requirements.md).

Measured on `cpm-stylebook` (`STYLEBOOK_ID = 14`) on 2026-11-18. This document is updated after each phase.
Closing lessons and product requirements are in
[`stylebook-organizations-requirements.md`](stylebook-organizations-requirements.md).

## Why organizations are not places or people

| Places | People | Organizations |
| --- | --- | --- |
| Geography can referee identity | Article context identifies a person | Official identifiers, aliases, hierarchy and time all matter |
| A branch is usually a place | Parent/child is not an identity question | Parent, division, chapter, branch, team and school may all be distinct actors |
| Same name often means the same place | Same name often means different people | Same name may be a duplicate, a namesake, or the same label at different hierarchy levels |
| A geocoder can resolve many conflicts | There is no general outside referee | Wikidata, official sites and registries can referee some conflicts, never decide alone |
| Wrong merge moves a pin | Wrong merge attributes actions to a person | Wrong merge collapses institutions and rewrites affiliations and relationships |

The organization rubric therefore needs four answers: **same**, **different**, **related but distinct**, and
**unsure**. Related organizations stay apart and should eventually be connected, not merged.

## Baseline

### Catalog and evidence

- 30,401 active canonicals. Creation was concentrated in four bulk-load days: 15,678 on Nov. 13, 6,976 on
  Nov. 16, 4,648 on Nov. 14 and 3,099 on Nov. 15.
- 20,207 canonicals have active article mentions (122,798 mentions total); 10,194 have no linked substrate
  organization.
- 12,475 canonicals have an open connection; 37,876 open connections touch an organization. Zero linked
  mentions therefore does not mean a row is inert.
- 6,890 canonicals have Wikidata metadata; 6,254 have Wikipedia metadata.
- Aliases: 35,722 `substrate_ingest`, 27,220 generated acronyms, 1,184 cleanup-AI, 494 UI link/accept,
  294 reviewed CSV merge aliases and 288 cleanup-merge aliases. Ingest aliases and generated acronyms are
  evidence for recall, not identity by themselves.

### Types

The largest types are sports team (5,391), company (3,882), nonprofit (3,645), local business (3,455),
government (2,046), culture/arts (1,702), community group (1,569), media (1,440), school (1,057) and
university (897). There are 807 `other` rows.

### Quality queues

- `duplicate-organizations`: 5,178 live edges in 2,900 clusters.
- 1,606 labels occur more than once. Only 222 label/type groups repeat; 1,406 labels span more than one type.
  Type inconsistency is a primary defect, not a safe identity veto.
- Examples of same-label mixed types: `Chicago Teachers Union` has five types; `Constellation` five;
  `Chicago Board of Education` four; `National Guard` four.
- `mismatched-organizations`: zero. This must be audited; the PostgreSQL trigram prefilter can exclude a
  textually similar but semantically wrong link before the final predicate sees it.
- Questionable-organization deterministic prefilter: 2,711. Leading signals are no organization anchor
  (2,711), culture/arts without an anchor (965), person-like (802), place-like (551), and law/program (157).
- Candidate queue: 88 pending rows, all deliberately deferred by the brand/platform boundary. Types are
  company (54), media (32), community group (1) and culture/arts (1).

## Goal

Make the organization catalog safe for editorial use and suitable as the identity layer for person
affiliations:

1. Fold real duplicates without flattening hierarchy, branches, teams, departments or namesakes.
2. Remove or reclassify things that are not durable organizations without losing article evidence.
3. Reconcile types after identity is settled.
4. Close the candidate queue under an explicit brand/product/platform rule.
5. Leave a small, named set that genuinely needs a person.
6. Turn the learned rules into product requirements, not permanent scratch scripts.

## Decisions and defaults

1. **Durable actor.** An organization canonical is an institution capable of acting, employing, governing,
   publishing, competing or holding relationships. A product, platform, event, law, work title, generic
   group or place is not an organization merely because article prose personifies it.
2. **Hierarchy stays apart.** Parent and child institutions, chapters, departments, school districts and
   schools, universities and teams, leagues and teams, and independently acting branches are distinct.
3. **Venue boundary.** A business venue may have an organization and a location identity. A chain outlet is
   a location unless it is an independently acting organization.
4. **Continuity.** A rename or rebrand with institutional continuity uses one canonical and dated aliases.
   A spin-off, acquisition target that remains distinct, or successor institution gets another canonical.
5. **Type is classification, not identity.** A type mismatch is evidence to review, not proof of sameness or
   difference. The canonical type describes the standing institution, not its role in one article.
6. **Alias trust.** Generated acronyms and ingest aliases may retrieve candidates but never decide identity
   alone.
7. **Conservative automation.** Exact label and type are not enough for an unattended fold. A rule fold
   needs a second independent signal and no veto; all other merges need two independent readers.

## Phases

### Phase 0: measure and label a seed set

- Snapshot every queue by type, evidence count, creation cohort, alias provenance, metadata and connections.
- Sample exact-label same-type and mixed-type groups, acronym matches, zero-evidence rows, government units,
  schools/teams, chapters/branches, sports segments and candidate boundaries.
- Audit linked rows to explain the zero mismatch count and establish a labeled seed set.
- Probe finder blind spots by trusted alias, external ID, one-letter variants and known hierarchy forms.

### Phase 1: make mutation and review tooling safe

- Merge contract: preserve source label and aliases with provenance, metadata, Wikidata/Wikipedia identifiers,
  type, connections and mentions; reject conflicting external IDs; record a before-state usable by undo.
- Finder contract: active rows only; scored edges and reasons; bounded blocks; explicit numeric, jurisdiction,
  hierarchy, branch, school/team, league/team, sport and gender-segment guards.
- Run contract: AI review uses the exact materialized run; surviving cached clusters are refreshed after a
  member changes; dismissals apply to detected edges, are versioned, validated and reopenable.
- Recall contract: search relevant candidates, not an alphabetic slice. Align substrate fingerprint and
  canonical normalization only with an explicit migration.
- Mismatch contract: PostgreSQL and SQLite evaluate equivalent candidate populations; project scope is
  honored consistently.

### Phase 2: deterministic duplicate tiers

- Use cheap rules first, but require two identity signals. Candidate signals: exact normalized label, trusted
  editorial alias, matching external ID, compatible type, matching jurisdiction, and article context.
- Hard vetoes: conflicting external IDs; different numbers or jurisdictions; parent/child or branch/parent;
  school/district; team/school or league; different sport or gender segment; incompatible contemporaneous
  institutions.
- Audit every proposed rule fold with a generic/common label, multiple projects or source metadata.

### Phase 3: readers and consensus

- Packet: labels, types, aliases and provenance, finder reason, mentions and snippets, metadata/external IDs,
  connections, dates, and possible hierarchy relation.
- Two models independently answer `same`, `different`, `related_but_distinct`, or `unsure`, with confidence
  and one evidence sentence.
- Merge only when both say same, neither is low, one is high, no veto applies, and the whole merge group has
  no conflict. Dismiss only under the audited two-reader policy. Related and unsure pairs stay apart.
- Named outputs: rule folds, reader merges, dismissals, related pairs, vetoes, group conflicts and held pairs.

### Phase 4: wrong boundaries, zero-evidence rows and taxonomy

- Run the existing questionable prefilter and LLM review; require two readers before destructive action.
- Separate person, place, law/program, event/competition, creative work/topic, generic group and ambiguous
  institution cohorts.
- Do not silently delete linked evidence. Reclassify/re-extract when a destination catalog exists; otherwise
  retire with a reason and audit trail.
- Prune a zero-evidence row only when it has no editorial provenance, metadata, mentions or open connection.
- Reconcile mixed types only after identity; write standing-type rules from the observed cohorts.

### Phase 5: mismatch and candidate queues

- Repair wrong links before promoting aliases; audit ingest aliases and generated acronyms independently.
- For the 88 brand/platform rows: link only when the mention denotes an existing institution as actor; create
  only an independently acting organization; otherwise defer/waive with a boundary reason.
- Count by reason, type and “read or not” before declaring either queue closed.

### Phase 6: guarded apply and closing requirements

For every wave: dry run, targeted `pg_dump`, per-group transaction, shared functions, activity row, immutable
before-state ledger and semantic reindex. Verify mention/link counts, FKs, connections, metadata, aliases,
external IDs and candidate status invariants. Re-run the finder and confirm dismissed work does not return.

Close with `stylebook-organizations-requirements.md`: lessons, operating tiers, requirements OA through OF,
product decisions, metrics and remaining review lists.

## Results

The guarded waves completed on 2026-11-18:

- Candidate review: 88 packets; two readers agreed on 69 waivers and four links; 15 remain pending.
- Questionable-boundary review: 2,711 packets; 1,636 keeps and 68 retirements had two-reader agreement.
  Another 19 destructive proposals were held by live safety checks, and 988 rows lacked consensus.
- Duplicate review: 5,178 scored edges; consensus produced 2,065 merge groups covering 2,464 source
  canonicals, 577 dismissal decisions and 1,795 held edges. Transitive conflict checks vetoed 320 proposed
  groups. The apply wave completed 2,065 merges and 431 still-live edge dismissals.
- Zero-evidence review: 9,134 ingest orphans with no linked substrate, metadata, open connection or editorial
  alias provenance were retired to inactive status with before-state ledgers.
- Mismatch audit: all linked organization rows were evaluated under the same PostgreSQL and SQLite
  predicate. Twelve legitimate spelling or formatting aliases were promoted after review; the final queue is
  zero.
- Follow-up catalog audit: inactive audit rows are hidden from the default organization list, and a bounded
  compact-label key surfaced spacing-only variants such as `350 Chicago` / `350Chicago`. Two readers reviewed
  226 live exact-or-compact edges; 78 groups merged 91 source rows, three edges were dismissed and 110 were
  held. `19th Ward` remains held because its mentions do not establish one acting institution.

Final measurements: 18,644 active canonicals; 419 duplicate clusters / 775 edges; 307 zero-linked
canonicals; 274 questionable-prefilter rows; 15 pending candidates; zero name mismatches. All 122,821
linked organization mentions present at close remain attached to linked substrate organizations; no
existing mention was lost. Every remaining zero-linked canonical has metadata, an open connection or
editorial alias provenance.

Post-close mixed-type follow-up on 2026-11-18 reviewed all 81 remaining same-normalized-name groups whose
members had different types. Two independent readers agreed on identity for 68 groups; 73 source
canonicals were merged into one selected keeper and reconciled standing type. Thirteen groups remain
separate because they are namesakes, carry conflicting external identity evidence, or lack enough evidence
to establish identity. The wave preserved all 22,039 linked substrate organizations and 122,978 mentions
present immediately before it; active canonicals fell from 18,643 to 18,570 with no dangling aliases,
metadata or substrate links. The duplicate finder fell to 358 clusters and 698 live edges.

An alias-and-graph follow-up reviewed 185 same-type canonical-to-alias collisions after excluding generated
acronyms. Two readers approved 113 groups covering 115 sources; 70 edges were held, including all 33
external-metadata conflicts. Shared typed graph neighbors materially supported 48 approved merges, were
neutral for 67, and were misleading for four held hierarchy or sibling cases. A second high-signal
containment pilot used graph overlap, contiguous label tokens and stricter thresholds: 60 groups covering
62 sources merged, 24 edges were held and two transitive conflicts were vetoed. One additional
segment-implicit Stevenson football alias was merged after direct evidence review. Across both passes, 178
sources were removed while all 22,039 linked substrate organizations and 122,978 mentions were preserved.
Active canonicals fell to 18,392 and the finder to 327 clusters / 635 live edges, with no source references
or dangling substrate, alias or metadata rows.

The live finder queue was then reviewed edge by edge rather than treating its connected components as
identity groups. Two readers reviewed all 635 live edges with aliases, external metadata, mentions and
typed graph neighborhoods. The first guarded consensus merged 95 sources in 79 groups and dismissed 213
clearly distinct or related edges. A third-reader pass over every disagreement merged eight more sources
in five groups and dismissed another 65 edges. Transitive conflicts and low-evidence disagreements stayed
open. Across both passes, 103 sources were removed and 278 pair decisions were added while all 22,039
linked substrate organizations and 122,978 mentions were preserved. Active canonicals fell to 18,289; the
finder now has 150 clusters / 202 live edges, with zero dangling source references or open connections.

A final binary adjudication gave two blinded readers and a senior judge every remaining edge, with
insufficient identity evidence defined as keep separate. The judges proposed 90 pairwise merges, but the
component conflict pass rejected 82 because another edge inside the proposed identity component was
distinct or carried a hierarchy or facet veto. Eight safe source records were merged; 193 surviving edges
were dismissed as keep separate, and one adjudicated edge disappeared from finder detection after its
endpoint merge. The finder now has zero live edges and zero clusters. The final wave preserved all 22,027
linked substrate organizations and 122,978 mentions present immediately before it, leaving 18,271 active
canonicals with no dangling evidence or connections.

Each mutation wave used a dry run, targeted PostgreSQL backup, per-decision before-state ledger,
per-group transaction and activity record. Duplicate merges used the shared merge function and reindexed
moved substrate organizations. No dangling canonical foreign keys or connections, metadata conflicts, alias
losses or candidate status/FK violations remained in the closing checks.

## Product requirements already visible

- Alias inspection/add/suppress UI with provenance; safe rename; explicit source-label transfer on merge.
- Merge preview and undo covering aliases, metadata, external IDs, evidence and connections.
- `related_but_distinct` review outcome and a path to create the appropriate connection.
- Edge-level reasons, dismissal reason/reopen, algorithm version and run-pinned AI review.
- Consistent project scoping and PostgreSQL/SQLite mismatch behavior.
- Candidate reason models instead of loose JSON; complete `all` queue view.
- Alias-aware public search only as an explicit public API decision, with API Playground changes.
- Once organizations are clean, replace free-text person affiliation matching with organization canonical IDs.

## Risks

- Union-find can join A-B and B-C even when A-C is false.
- Cluster dismissal can suppress pairs the finder never proposed.
- A generated acronym can collide across unrelated institutions.
- Same address may be a tenant, parent, branch or venue; different address may be the same institution.
- Cached run labels and membership can become stale after merges.
- A merge path that bypasses the shared organization merge can still lose source-only aliases or metadata.
- The cleanup UI and canonical detail UI have different delete permissions and linked-evidence behavior.
- Model omission in a partially failed questionable batch can look like “keep.”

## Validation

Targeted finder, merge, recall, mismatch, policy, candidate API and UI tests during each phase. Before handoff:
`make lint`, `make test`, and `make smoke` for runtime/integration changes, followed by Backfield code and
architecture reviews.
