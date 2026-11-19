# Organizations: lessons and requirements (closing summary)

**Status:** Planning only; nothing here is a runtime contract. Closes the organization work in
[`stylebook-maintenance-program.md`](stylebook-maintenance-program.md) (Category 7, decisions D21 to D24).
Evidence and the measured procedure are in
[`stylebook-organizations-maintenance.md`](stylebook-organizations-maintenance.md); the reusable method is in
[`stylebook-agent-maintenance.md`](stylebook-agent-maintenance.md). Requirement IDs use an `O` prefix so they
stay separate from places and people.

Measured on `cpm-stylebook` (`STYLEBOOK_ID = 14`), 2026-11-18.

| Measure | Start | Close |
| --- | --- | --- |
| Active organizations | 30,401 | 18,644 |
| Duplicate finder | 2,900 clusters / 5,178 edges | 419 clusters / 775 edges |
| Zero-linked canonicals | 10,194 | 307 |
| Questionable prefilter | 2,711 | 274 |
| Pending candidates | 88 brand/platform boundary rows | 15 held rows |
| Name mismatches | 0 reported but unverified | 0 after full-population audit |
| Linked organization mentions | 122,798 | 122,821; none lost |

Applied waves used a targeted PostgreSQL backup, a dry run, per-decision before-state ledger, shared
merge/link functions, activity rows and semantic reindex for moved substrate organizations. The scratch
packets, reader outputs and ledgers remain under `tmp/stylebook-agent-cleanup/organizations/` and are not
product contracts.

A post-close mixed-type pass reviewed the remaining 81 same-normalized-name groups across different
types. Two readers agreed to consolidate 68 groups, removing 73 duplicate source canonicals while
preserving all 22,039 linked substrate organizations and 122,978 mentions present before the wave. The 13
held groups are genuine namesakes, external-identity conflicts or evidence-poor ambiguities; type
disagreement alone no longer keeps an approved duplicate alive. The duplicate finder fell to 358 clusters
and 698 live edges.

The subsequent alias-and-graph pilot found 185 same-type canonical labels that exactly matched a
non-generated alias on another active canonical. Consensus merged 115 sources; graph overlap materially
supported 48 of those decisions but was neutral for 67 and misleading for four held parent/child or sibling
pairs. A stricter graph-plus-contiguous-label expansion merged another 63 sources, including the remaining
Stevenson school and team aliases. Both passes preserved all 22,039 linked substrate organizations and
122,978 mentions, leaving 18,392 active canonicals and 327 duplicate clusters / 635 live edges.

A full review of those 635 live finder edges subsequently merged 103 sources in 84 guarded groups and
dismissed 278 clearly distinct or related pairs. The initial two-reader pass covered every edge; a
third-reader pass adjudicated the remaining disagreements without relaxing metadata, hierarchy, facet or
transitive-conflict vetoes. All 22,039 linked substrate organizations and 122,978 mentions were preserved.
The catalog now has 18,289 active canonicals and 150 duplicate clusters / 202 live edges held for stronger
evidence.

A final binary pass used two new blinded readers and a senior judge, defaulting to keep separate whenever
identity was not affirmatively established. Although the judges proposed 90 pairwise merges, component
safety rejected 82 because another edge in the proposed group was distinct or carried a hierarchy or facet
veto. Eight safe sources merged, 193 surviving pairs were dismissed, and one pair disappeared after its
endpoint merge. The finder is now at zero live edges / zero clusters. The wave preserved the 22,027 linked
substrate organizations and 122,978 mentions present immediately before it, leaving 18,271 active
canonicals.

## What we learned

1. **An organization is a durable actor, not every capitalized brand-like noun.** Products, platforms,
   streaming services, apps, events, laws, works and generic groups accounted for the whole initial candidate
   queue and a material part of the questionable prefilter.
2. **Hierarchy is the central organization trap.** Parent/child institutions, chapters, departments,
   school/district, university/team, league/team and independently acting branches may share every name token
   and still must remain separate.
3. **Related is not different.** Review needs `related_but_distinct` as a first-class outcome so a hierarchy
   relationship is not hidden inside a generic dismissal and never becomes a merge.
4. **Type is too noisy to decide identity.** Of 1,606 repeated labels, 1,406 crossed types. The same standing
   institution had been classified from its role in different articles; unrelated namesakes also shared a
   type. Type is evidence to reconcile only after identity.
5. **Exact label and type are not enough.** Common labels and independently named local institutions still
   collide. The unattended deterministic tier produced only 36 edges after requiring shared metadata as a
   second signal.
6. **External IDs are excellent positive evidence and mandatory negative evidence.** Matching Wikidata or
   Wikipedia values strengthened 724 finder edges; 101 edges had conflicting metadata and were hard-vetoed.
   Merge must fail before relinking anything when values conflict.
7. **A merge that deletes the source must first move more than mentions.** Source aliases, suppression state,
   provenance, metadata, external IDs, type and primary evidence were previously lost. Connections were
   already rewired, but the rest needed a shared contract.
8. **Candidate recall was accidentally alphabetical.** The organization recall helper scored only the first
   96-or-more labels in label order. A relevant canonical later in the alphabet could never be suggested.
9. **A database optimization changed the mismatch contract.** PostgreSQL applied a trigram floor before the
   shared semantic predicate, while SQLite evaluated the full linked population. Zero reported mismatches
   therefore needed an audit, not trust.
10. **Inactive rows must disappear from quality work.** The duplicate profile loader did not filter status,
    so retired canonicals could return as fresh clusters.
11. **Scored edges are the review unit, not every possible pair in a transitive cluster.** Dismissing a whole
    cluster writes pair dismissals the finder never proposed and can hide future evidence.
12. **Transitivity needs a conflict pass.** A-B and B-C reader merges do not imply A-C. Any different,
    related, unsure or vetoed edge inside a proposed group holds the group.
13. **Zero linked mentions is not zero evidence.** At baseline, 147 zero-linked canonicals still had open
    connections, 78 had metadata and 259 had editorial alias provenance.
14. **Two readers expose product-versus-actor ambiguity.** The candidate readers agreed on 69 waivers and
    four links, and held 15 rows such as Facebook, Twitter, OpenTable and Apple Music where a service name
    sometimes denotes the operating company. The durable-actor rule kept those disagreements pending.
15. **A held row is a valid resolution state.** Forcing a product/actor disagreement would either create
    product canonicals or attribute a company's actions to a service. The queue must show the evidence and
    ask for a person.
16. **Inactive audit rows should not look like live duplicates.** Retirement preserves the canonical for
    audit and undo, but the default Stylebook list must show active rows unless an operator explicitly asks
    for inactive history.
17. **Spacing compaction is a small, high-value blocking key.** A minimum-eight-character compact form
    surfaced 33 missed pairs across 30 groups, including `350Chicago`, `CWBChicago` and `SiriusXM`, without
    making compact text sufficient for an unattended merge.
18. **A type mismatch must not keep an approved duplicate alive.** Selecting the keeper also selects its
    standing type by default; an operator may explicitly override that type when the source classification
    is better supported. Identity review still happens before this taxonomy decision.
19. **The graph is corroboration, not identity.** Shared typed neighbors strongly supported aliases when
    labels and facets agreed, especially shared locations, opponents, people and memberships. The same
    signal was misleading for sibling teams, hierarchy, venues/operators and divisions. Missing graph
    evidence was neutral because coverage is sparse.
20. **Canonical-label-to-alias collisions are a productive candidate source.** Excluding generated
    acronyms produced a bounded review set across schools, teams, government, media, hospitals, venues and
    companies. Ingest aliases generated candidates but never decided merges; external-ID conflicts and
    sport, segment, hierarchy and predecessor/successor guards remained mandatory.
21. **Queue size includes known non-duplicates until negative decisions are recorded.** Reviewing every
    scored edge reduced the live queue through both guarded merges and explicit distinct/related dismissals.
    Connected-component cards remain a presentation convenience, not evidence that every member shares one
    identity; disagreements and transitive conflicts must remain visible instead of being force-resolved.
22. **Binary pairwise votes still require global consistency.** The final judges proposed 90 merges, but
    only eight survived the component conflict pass. A model can correctly recognize A-B as aliases while a
    separate B-C edge proves the proposed component unsafe; automation must validate every internal edge
    and prefer keep separate over transitive over-merging.

## Operating model

| Tier | Rule |
| --- | --- |
| `rule_merge` | Same normalized label and standing type, a matching external ID or equally independent signal, and no veto |
| `reader_merge` | Two models say `same`; neither low; one high; no hard veto or group conflict |
| `reader_dismiss` | Two models agree `different` or `related_but_distinct`; neither low; one high |
| `reader_retire` | Two models agree on the same wrong boundary and the canonical has no linked evidence, metadata, connection or editorial provenance |
| `rule_retire_orphan` | No linked substrate, metadata, open connection or editorial alias provenance; retain a before-state and inactive row |
| `held` | Readers split, either is low, evidence conflicts, a group conflict exists, or a destructive action would strand evidence |

Hard vetoes after readers: conflicting external IDs or metadata, different jurisdictions or unit numbers,
parent/child or branch/parent, school/district, team/school or league, different sport or gender segment, and
any non-same verdict inside a proposed merge group.

Apply protocol: materialize the exact scored-edge run; two independent reader outputs keyed to it; consensus;
veto and group checks; dry run; targeted backup; before-state ledger; per-group transaction; shared merge,
link and dismissal functions; activity row; semantic reindex; and post-wave integrity queries.

## Requirements by spec

### OA. Ingest and canonicalization prevention

| ID | Requirement | Evidence |
| --- | --- | --- |
| OA1 | The shared organization merge preserves source label and aliases with provenance and suppression, metadata/external IDs and primary evidence; it rejects unresolved metadata conflicts before relinking and uses the selected keeper's standing type unless explicitly overridden | Source rows were deleted with those fields; mixed extraction types otherwise blocked approved merges |
| OA2 | Ingest creates an organization only for a durable acting institution; product, platform, event, law, work, generic group and place boundaries get typed reason codes instead | All 88 initial candidates were boundary deferrals |
| OA3 | Parent/child, chapter, department, school/district, university/team, league/team and independently acting branch identities remain separate; capture their relationship | Highest-risk false merge pattern |
| OA4 | Canonical type describes the standing institution, not the role in one article; reconcile type only after identity | 1,406 repeated labels crossed types |
| OA5 | Substrate fingerprints and canonical matching use one versioned normalization; changing it requires a collision report and data migration | Current normalization paths differ |
| OA6 | A rebrand with continuity keeps one canonical and dated aliases; spin-offs and successors remain separate | Reader rubric needed a time rule |

### OB. Review queue, finder and recall

| ID | Requirement | Evidence |
| --- | --- | --- |
| OB1 | Duplicate profiles include active canonicals only | Fixed during this round |
| OB2 | The API exposes the actual accepted edge, score, signal scores and human-readable reasons | The finder already computed reasons but discarded them |
| OB3 | Bounded blocks and tests cover hierarchy, jurisdiction, branch/chapter, numbered units, school/team, league/team, sport/gender segment, acronym collision, rebrand and one-letter variants | Organization-specific failure modes |
| OB4 | Recall searches candidates relevant to the mention and exact aliases, never an alphabetic catalog slice | Fixed; late-alphabet regression test added |
| OB5 | PostgreSQL and SQLite mismatch checks evaluate the same candidate population before the shared predicate | Fixed by removing the PostgreSQL-only trigram exclusion |
| OB6 | Dismissals store edge reason, finder/rubric version and evidence hash; list and reopen them when the algorithm or evidence changes | Current table stores only pair keys |
| OB7 | AI review is pinned to one materialized run; cluster labels and membership refresh after every merge, retirement or deletion | Cached payloads become stale |
| OB8 | Generate bounded candidates when an active canonical label matches a non-generated alias on another canonical; include alias provenance but never treat it as an identity verdict | 185 useful cross-label candidates remained outside label-only blocking |
| OB9 | Add typed/directed graph-neighborhood evidence to review packets and scoring, with explicit hierarchy, sibling, venue/operator and predecessor/successor warnings; graph absence is neutral | Graph helped 48 alias decisions and misled four held edges |

### OC. Review with AI

| ID | Requirement | Evidence |
| --- | --- | --- |
| OC1 | Packets include labels, standing types, aliases and provenance, mention counts and samples, substrate labels, metadata/external IDs, connections and finder reasons | Each changed verdicts |
| OC2 | Organization verdicts are `same`, `different`, `related_but_distinct`, or `unsure`, with confidence and a short evidence reason | Binary review cannot represent hierarchy |
| OC3 | Merge only under the two-reader policy above; apply vetoes after readers and check complete transitive groups | Reader agreement alone is not enough |
| OC4 | Questionable-boundary retirement needs two readers agreeing on the boundary category and a live no-evidence check | Avoids deleting linked evidence |
| OC5 | Treat article text and model outside knowledge as evidence, not authority; external IDs can referee but never override a conflict | Namesakes and stale descriptions exist |
| OC6 | Persist every reader decision, model, confidence, reason, packet/run ID, rubric version and consensus tier | Scratch outputs were required to audit the wave |

### OD. Agent API, auth and undo

| ID | Requirement | Evidence |
| --- | --- | --- |
| OD1 | Merge preview returns aliases, metadata, external IDs, substrate rows, mentions, connections and type changes, with dry-run validation | The cleanup UI currently previews less than the merge moves |
| OD2 | Undo recreates the source and restores every before-state field and edge; merged IDs retain a `merged_into` lookup | A database backup is not product undo |
| OD3 | Dismiss and reopen operate on validated detected edges, not all possible pairs in a cluster | Transitive clusters contain unscored pairs |
| OD4 | `related_but_distinct` can create or propose the correct organization connection | A dismissal alone loses hierarchy knowledge |
| OD5 | Alias UI supports inspect, add, suppress, provenance and safe rename; merge preview shows source-label transfer | Alias trust governed mismatch and recall |
| OD6 | Candidate decision endpoint supports link, create, waive and hold with boundary reason codes, a before-state ledger and undo | 69 waivers, four links and 15 holds |

### OE. Evaluation and operations

| ID | Requirement | Evidence |
| --- | --- | --- |
| OE1 | Maintain labeled organization sets for namesakes, hierarchy, branches, schools/teams, government units, rebrands, products and wrong boundaries | Finder tests cover only part of the rubric |
| OE2 | Measure precision by tier and audit random merges, dismissals and retirements before unattended scheduling | This round used consensus and named holds, not a calibrated error rate |
| OE3 | Metrics include live edges/clusters, resolution tier, veto/group-conflict count, reader agreement, held rate, zero-evidence cohorts and queue read state | These were manual counts |
| OE4 | Every mutation wave requires dry run, targeted backup, per-group transaction, immutable ledger, activity and reindex status | Used successfully in this round |
| OE5 | Runs are incremental by changed canonical, edge evidence and candidate watermark; a finder version change reopens affected edges in shadow mode | Full-catalog review is too expensive |
| OE6 | Integrity checks compare mention/substrate totals, dangling FKs and connections, alias/metadata counts, external-ID conflicts and candidate status/FK invariants | Each catches a different loss mode |

### OF. Category playbook

1. Define the durable actor and hierarchy boundaries before sampling.
2. Measure repeated labels across types; do not assume type is an identity veto.
3. Repair merge preservation, edge observability, recall and database parity before data changes.
4. Materialize edges, use two independent readers, then apply vetoes and transitive conflicts.
5. Clean wrong boundaries and zero-evidence rows separately from duplicate identity and taxonomy.
6. Close candidates under the same actor rule and keep product/company ambiguity visible.

## Product decisions to make

| # | Decision | Recommendation |
| --- | --- | --- |
| 1 | Organization hierarchy representation | Typed organization-to-organization connections; never merge to express hierarchy |
| 2 | Canonical organization type | Standing institution taxonomy with article role per mention |
| 3 | Brand and platform policy | Canonicalize the operating institution; retain product/platform names as mention-level roles or aliases only when unambiguous |
| 4 | Agent autonomy | Two-signal rule merges and two-reader dismissals now; reader merges and retirements only after a measured audit rate |
| 5 | Dismissal lifetime | Reopen when finder/rubric version or evidence hash changes |
| 6 | Public alias search | Make it an explicit public API decision and update API Playground in the same change |
| 7 | Person affiliation | Replace free text with organization canonical IDs after the organization requirements are built |
| 8 | Zero-evidence retention | Keep inactive audit rows with undo until product retention policy exists |

## Open after organizations

- The duplicate finder is at zero live edges; its pair-key dismissals still need reason, evidence-hash and
  finder-version metadata so changed evidence can reopen them safely.
- 274 questionable-prefilter rows held as ambiguous institutions or weak boundary signals.
- 307 zero-linked canonicals retained because each has metadata, an open connection or editorial alias
  provenance.
- The 15 held brand/platform candidates, with both reader reasons in the scratch review list.
- Standing type reconciliation for identities that crossed types; do not use bulk relabeling without an
  approved taxonomy.
- Product work OA through OF. Scratch scripts are prototypes, not supported operations.
