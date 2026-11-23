# Stylebook cleanup toolkit (planning)

**Status:** Planning. Nothing here is a runtime contract. Written 2026-11-23, after the 2025 and 2024
cleanups of places, people, and organizations on `cpm-stylebook`.

This plan turns those cleanups into repeatable, transparent tooling that can run against any
Backfield instance the operator holds an API key for, including instances they do not control.

**Who owns what.** Backfield provides a surface (operations, reads, instance protections, ingest
prevention, and operator repairs) and is unopinionated about how tools use it. The cleanup
toolkit lives in its own repository and owns everything about how a cleanup is carried out:
phases, judgment, review, staleness, and whether a run was complete and correct. Stream 2 and the
toolkit parts of the findings register are the design for that repository and move there when it
exists. Streams 1, 3, and 4 are Backfield's work. See
[`stylebook-cleanup-api.md`](stylebook-cleanup-api.md#what-backfield-owns-and-what-it-does-not).

It organizes three streams of work and one shared discipline:

1. **Prevention:** what the regular ingest and standardization path should do so the problems stop
   being created.
2. **The cleanup toolkit:** an outside repository (skills, a tested engine, and a thin MCP server)
   that finds problems, runs model readers, decides, and applies through the API.
3. **The Backfield API surface:** the keyed endpoints in this repo that the toolkit needs. Planned
   in its own document, [`stylebook-cleanup-api.md`](stylebook-cleanup-api.md).
4. **The discovery loop:** how a new finding becomes prevention, a rule, an endpoint, or an
   operator repair, so the API does not sprawl.

It extends, and does not replace:

- [`stylebook-maintenance-program.md`](stylebook-maintenance-program.md): decision log and specs A-F.
  This plan fills in spec A (prevention), and adds decisions D29-D45 there. Spec D (agent API,
  auth, undo) is filled in by [`stylebook-cleanup-api.md`](stylebook-cleanup-api.md).
- [`stylebook-agent-maintenance.md`](stylebook-agent-maintenance.md): the places case study and the
  first endpoint sketch.
- [`stylebook-maintenance-job-catalog.md`](stylebook-maintenance-job-catalog.md): the 48 discrete
  jobs. The toolkit skills below are families of those jobs.
- [`stylebook-autonomous-year-cleanup.md`](stylebook-autonomous-year-cleanup.md): the runbook the
  `start-run` skill encodes.

## Principles

1. **Prevent first, clean second.** Follow the ladder in the program doc: prevent at ingest, then
   deterministic rules, then review-queue logic, then AI review, then a person.
2. **The API is the only write path.** The toolkit never writes with SQL or by importing Backfield
   packages. Data-model invariants, the UI's own per-item guards, and instance protections (dry
   run, ceilings, a kill switch, a ledger, undo) live once, on the server. Judgment rules (reader
   consensus, vetoes beyond what the UI enforces, the sensitive-type policy) and completeness
   checks live in the toolkit.
3. **The API is model-free.** The toolkit brings its own models (program decision D1). The server
   serves evidence and accepts decisions with their provenance.
4. **The server never acts on its own.** There is no server-side auto-apply. Deterministic verdicts
   are advisory evidence the toolkit may use to skip model readers on obvious cases.
5. **Assessment, decision, mutation, and verification stay separate.** Only apply steps mutate.
6. **Everything leaves an inspectable artifact.** A run is a folder of plain files that a person
   or a coding agent can read, so transparency does not depend on a particular interface.
7. **Evidence is untrusted text.** Article snippets can try to steer a model that can merge. Keep
   packets marked as data and the toolkit's tools narrow.

## Decisions recorded here

Also added to the program doc's decision log.

| # | Decision |
|---|----------|
| D29 | External tools authenticate with a project API key and call a keyed cleanup namespace under `/public/v1`. The browser-session and service-token cleanup routes stay for the Stylebook UI. |
| D30 | The toolkit is API-only. SQL is for local exploration on an instance the developer controls, never in a skill or in the toolkit's runtime path. Reusable findings are promoted into endpoints or checks. |
| D31 | Model calls run in the toolkit repository. The API runs no models for the toolkit. The in-product "Review with AI" feature is unaffected. |
| D32 | `auto_safe` is advisory. No server-side setting applies merges unattended. Unattended runs are a scheduling choice of the toolkit. |
| D33 | New findings pass through the discovery loop (below) before any new endpoint is added. Prefer a new check, rule, or rubric over a new apply verb. |

Decisions D34-D45 (per-operation apply routes, service-key apply scope, export route, path shape,
the preview launch, the division of responsibility, retirements and deletions, project scope, and
the lightweight run) concern the API and are recorded in
[`stylebook-cleanup-api.md`](stylebook-cleanup-api.md#decisions-recorded-here).

## Architecture at a glance

```text
ingest (this repo)        prevents most bad records at creation
        |
Stylebook data  <---- keyed cleanup API (this repo, /public/v1) ----> cleanup toolkit (outside repo)
        ^                                                              skills + engine + MCP + models
        |
operator lane (this repo): backfield CLI repairs for data defects that need database-level work
```

Four lanes, each with a clear owner:

| Lane | Lives in | Does |
|---|---|---|
| Prevention | `packages/backfield-entities`, worker ingest | Does not create the bad record, or resolves it on the fly |
| Keyed API | Routes in `apps/core-api`; logic in `packages/backfield-entities` | Evidence reads, guarded apply, ledger, undo |
| Toolkit | Outside repository | Recall, readers, consensus, vetoes, closure, reports |
| Operator | `backfield` CLI and migrations | One-off data repairs a remote key must not perform |

## Stream 1: Prevention in ingest and standardization

Each row comes from a measured case. Owner is spec A or B in the program doc.

| Problem seen | Evidence | Prevention |
|---|---|---|
| **Parallel ingest mints duplicates** | 252 of 811 exact-label place duplicate groups were created less than 10 seconds apart; people and organizations showed the same shape | Serialize "create a canonical" per Stylebook, entity type, and normalized name, and re-check for an existing match inside the lock. A unique index is not enough because legitimate same-name places exist |
| **Pending status with a link left in place** | 4 mentions (two `Monona Bay`) blocked a merge; a lost update between workers | Row locking or a conditional update when ingest links or defers; the check reports any survivors |
| **Normalization differs between ingest, finder, and checks** | Accents, curly apostrophes, hyphens, slashes, spacing, and word order hid 90 groups | One shared fold function used by ingest lookup, the finder, and the mismatch checks |
| **Exact match defers on ambiguity** | `ambiguous_exact_canonical_match` queues review for every duplicate | Reuse pair classification as the commit gate so clear cases link and only unclear ones queue |
| **Gate false positives** | 154 place candidates sat in review with a 0.93-0.99 match because the content-sanity gate refused to link | Do not block a high-confidence match on name similarity when the rationale and geocode agree |
| **Recreated after a reviewed alias** | 849 active pairs where one label was already a trusted alias of the other; 337 sources created after the alias existed | Hardened 2026-11-22 (alias provenance cannot be downgraded; trusted alias planning first). Still needed: a metric and structured warning when materialization is attempted while a compatible trusted alias exists. Steady state is zero |
| **Region and natural-feature estimates beside real records** | 76 finder clusters | The real record wins at ingest: link to it instead of minting an estimate |
| **Invented state suffixes, echoed addresses, wrong-state geocodes** | `Nueva York` landed in California; a Greenland "Library Club" | Reject a first geocode outside the state or country the label names; resolve known foreign-language names before geocoding; ask the geocoder for English |
| **Structured entities named many ways** | All 371 district canonicals had empty `district_kind`, `district_number`, `district_key` | Parse and fill the key at creation so the existing exact lookup resolves every future wording |
| **Geometry written in one form only** | 8,641 canonicals had `geometry_json` but no PostGIS geometry | Write both forms together everywhere; add a health check for JSON-only rows |
| **Merge-created aliases not trusted by checks** | 98% of the mismatched-places list was caused by our own merges | Writing the old name as a trusted alias is part of the merge; checks trust it |
| **Candidates that should never exist** | 721 of 2,193 people candidates fell to simple rules (relationships plus first name, handles, initials) | Do not queue relationship-plus-first-name or bare first names with no title or affiliation; do not create chain candidates without a street address |
| **Organization boundary** | Products and platforms treated as institutions; hierarchy flattened | Apply the hard-veto set (external ID conflict, hierarchy, numbers, segment) in the ingest gate, not only in cleanup |

Boundaries:

- Ingest stays deterministic and cheap. Model adjudication stays out of the hot path.
- Prevention is measured. Add "new duplicates per ingest run" and "deferrals per run" as metrics.
  Prevention is working when a later cleanup finds little left to do.
- Move deterministic pair classification into `packages/backfield-entities` so ingest, the check,
  the UI, and the API return the same verdict.

## Stream 2: The cleanup toolkit (outside repository)

### Layout

```text
backfield-cleanup/
  skills/                 plain-markdown runbooks, one per job family
  rubrics/                versioned reader rubrics
  engine/                 tested Python: recall, packets, consensus, vetoes, closure
  mcp/                    thin MCP server: one tool per API operation
  runs/<instance>/<run_id>/   artifacts for each run
```

Why this split:

- **Skills are the transparent layer.** A person can read one and see the steps, the guardrails,
  and when it stops. Skills carry the reasons and call the engine; they do not hide logic.
- **The engine holds the repeatable logic.** Consensus (both agree, neither low, one high), hard
  vetoes after the readers, the transitive component-conflict check, and the closure loop need unit
  tests. Prose drifts. Today these live in `tmp/` scratch scripts; promoting them to a tested module
  is the main extraction job.
- **MCP stays thin.** Each tool maps one-to-one to an API operation with no decision logic. The same
  operations then work from a coding agent, a command line, or a future UI.
- **Rubrics are versioned files.** The run manifest records the rubric version and model for every
  reader, which makes a run reproducible and auditable.

### Skills

About seven skills, each covering a family of catalog jobs.

| Skill | Covers | Notes |
|---|---|---|
| `start-run` | Foundation jobs: resolve target, check capabilities and scopes, establish cohort and watermark, baseline inventory, cost cap (the server run opens later, at apply time) | Interviews for every required input and refuses to proceed on a missing answer (see below) |
| `places-duplicates` | Recall packets, two blinded readers, consensus, vetoes, dry run, apply, bounded closure, final binary pass | Includes the address-to-place and district sub-modes |
| `people-duplicates` | Same loop, plus rule folds and the sensitive-type policy (D16, D20) | Sensitive person types are never merged by the toolkit without an owner list |
| `orgs-duplicates` | Same loop with `same` / `different` / `related_but_distinct` / `unsure`; type is classification, not identity | Hierarchy stays apart |
| `questionable-and-mismatches` | Questionable canonicals, mismatched links, missing geometry | Different rubrics and apply verbs |
| `candidates` | Candidate queues by entity type: scope rules first, then readers | Waives need a blind sample read by the second reader |
| `verify-and-report` | Integrity checks, audit sample, residuals, cost, report | Independent of the apply steps |

`start-run` inputs (from the autonomous-year runbook): instance, Stylebook, entity types, cohort
(year or watermark), read-only or apply mode, model choices per reader role, budget cap, and an
explicit acknowledgement that article snippets will be sent to the chosen model providers. A
missing answer stops the run. Never default to a particular instance.

### Patterns every skill follows

- Separate assess, decide, apply, and verify steps. Only apply steps mutate.
- Two blinded readers from different models, then deterministic consensus; hard vetoes run after
  the readers; a blind sample read by the second reader backs any single-reader dismissal.
- Generous recall first, then precision. "Keep separate" is the default when anything is unclear.
- Dry run before apply, per-item results, a re-read of affected canonicals just before applying a
  plan that waited (the server does not check staleness), and a ledger.
- Phases are the toolkit's choice and have no server state (API decision D39): investigate (reads),
  adjudicate (models), optional review, apply, verify. The toolkit enforces its own plan limits,
  and opens a server run when it starts applying. Whether and when to stop for review (for example,
  only on held items) is decided in the toolkit repository.
- The toolkit validates its own runs: no SQL, every `tooling_gap` listed, a result for every item,
  clean integrity reads, an undo sample, and queue reductions in the expected range.
- Bounded closure iterations (at most three), then a final binary pass.
- Scope rules before readers for candidate queues (decision D10).
- Cost recorded per reader call: model, tokens, and price.

### Run artifacts and transparency

Every run writes the same folder, so any interface can render it:

```text
runs/<instance>/<run_id>/
  manifest.json      instance, Stylebook, cohort, capabilities, models, rubric versions, caps
  packets/           evidence packets as read by the models
  readers/           raw reader outputs
  decisions/         consensus results and vetoes, with reasons
  ledger.jsonl       every apply attempt: request, response, before-state reference
  report.md          counts, residuals, held lists, audit sample, cost
```

The first interface is a coding agent that reads and narrates the folder, which is how the 2024
runs worked. A static report page can render the same files without a backend. A Stylebook UI view
becomes sensible only after the run record exists on the server and the format has held steady
across several runs.

## Stream 3: The Backfield API surface

The keyed API the toolkit calls has its own plan:
[`stylebook-cleanup-api.md`](stylebook-cleanup-api.md). It covers credentials and scopes, the route
catalog with phases, the shared apply envelope, server-side guarantees, where each route and its
logic live in the code, the shared merge fixes, and the preview launch (decisions D29 and D34-D45).

What the toolkit relies on, in brief:

- **Reads without SQL.** A capabilities route, a bulk canonical export, evidence and compare routes,
  check results, and the candidate queue. The toolkit builds its own recall groupings from the
  export and fetches snippets only for groups that need readers.
- **One apply path per operation.** Merge, edit, retire, delete, alias, dismiss, relate, relink, and
  candidate decisions, each with `dry_run` on by default. The instance is protected by operator
  ceilings per run, a kill switch, a before-state ledger, and undo. Per item, the API enforces what
  the UI enforces and the data-model invariants of the operation.
- **Service-key apply.** `cleanup:read` works on any key; `cleanup:apply` needs a service key.
- **A preview contract.** The routes are not in the public OpenAPI or the Playground. The toolkit
  reads a keyed schema and refuses to run against a preview version it does not know.

## Stream 4: Operator lane

Some findings are data defects that need database-level work and should not be offered to a remote
key. The toolkit detects them through a check and stops with a clear message ("this instance needs
operator repair X first"). The instance owner runs the repair through the `backfield` CLI or a
migration in this repo.

Seed list:

- Rebind PostGIS geometry for imported canonicals (`scripts/rebind_location_postgis_geometry.py`).
- Repair mentions that are `pending` while still linked to a canonical.
- Backfill district keys on existing district canonicals.
- Any one-off backfill that needs the shared library with side effects.

## The discovery loop and findings register

SQL exploration on a local instance stays the way new problems are found. Before building anything
for a finding, classify it:

| What was found | Where it goes |
|---|---|
| A recurring cause of bad records | Prevention (stream 1) |
| A new way to find suspects | A check (read-only), or a recall rule in the toolkit |
| A judgment readers get wrong | A rubric change, then a toolkit veto; if the UI should refuse it too, a fix to the shared merge guard |
| A fix the primitives cannot express | A new endpoint, or a new field on an existing one |
| A data defect in existing rows | An operator repair, plus a check that reports it |

Promote a finding when it recurs (a second year or a second instance) or when it blocks an apply.
A new problem class should change the toolkit and rarely the API. This register is also the
transparency artifact for why each rule and endpoint exists. Add a row for every finding.

| # | Finding | Class | Owner | Status |
|---|---|---|---|---|
| F1 | Parallel ingest mints duplicate canonicals | Prevention | Spec A | Not started |
| F2 | Pending status with a link left in place (lost update) | Prevention + operator repair | Spec A | Not started |
| F3 | Normalization differs across ingest, finder, and checks | Prevention | Spec A, B | Partly done (finder learned several folds) |
| F4 | Region and natural-feature estimates beside real records | Prevention + finder rule | Spec A, B | Finder rule applied by hand; ingest not started |
| F5 | Invented state suffixes and wrong-state geocodes | Prevention | Spec A | Not started |
| F6 | Merge drops aliases, geography, metadata, or closes connections | API (shared merge) | Spec A, D | Done in phase A (`merged_into` pending, phase C) |
| F7 | Recreated canonical after a reviewed alias | Prevention | Spec A | Hardened 2026-11-22; metric and warning open |
| F8 | District keys empty on all 371 districts | Prevention + operator repair | Spec A | Not started |
| F9 | JSON-only geometry on 8,641 canonicals | Prevention + operator repair + check | Spec A, E | Rebound by script; writer and health check open |
| F10 | `location_merge_pair_blocked` allows 169 of 182 mixed-kind pairs | Shared merge guard (UI and API) | Spec D | Done in phase A |
| F11 | Dismissals have no reason, are Stylebook-wide, and cannot be listed or reopened | API | Spec D | Not started |
| F12 | Before-state saved after mutation in one script | API (ledger) | Spec D | Learned; ledger design open |
| F13 | Semantic reindex not queued for merges applied through the library | API | Spec D | Done for merges in phase A (shared apply function) |
| F14 | Candidate queues are mostly records that should never exist | Prevention + toolkit scope rules | Spec A, toolkit | Rules applied by hand |
| F15 | Gate blocks good matches (content-sanity) | Prevention | Spec B | Not started |
| F16 | Finder is blind to nicknames, quoted nicknames, compound surnames | Finder rule | Spec B | Done in later rounds |
| F17 | Organization type differences are not identity vetoes; hierarchy stays apart | Rubric + toolkit veto | Spec C, D | Rubric done; toolkit veto open |
| F18 | Sensitive person types need owner approval | Toolkit policy | Spec D | Toolkit policy only |
| F19 | A single reader's dismissals need a blind audit by a second reader | Toolkit pattern | Toolkit | Encoded in plan only |
| F20 | Merging can move a bad shape onto good mentions | API (survivor shape check) | Spec D | Not started |

## Phasing

The toolkit and prevention work interleave with the API phases. API phases 0, A, B, C, and E are
detailed in [`stylebook-cleanup-api.md`](stylebook-cleanup-api.md#phasing).

| Phase | Work | Gate |
|---|---|---|
| 0 | API: scopes and the preview tag filter (see the API plan) | Scopes mintable on the right key types; preview routes absent from the public OpenAPI |
| A | Prevention: ingest serialization, shared normalization. API: shared merge fixes | Unit tests from the logged cases; UI benefits immediately |
| B | API: read routes | A toolkit prototype can build packets from the API alone |
| C | API: apply surface, in slices, covering every operation the 2024 runs used | Operation tests pass for each slice; the UI routes still behave the same |
| D | Toolkit repo: extract the scratch scripts into the tested engine, write `start-run` and the three duplicate skills, add the MCP wrapper | Engine tests from recorded decisions reproduce the recorded plans; a second pass proposes almost nothing |
| C2 | API: candidate decisions, mention links, and relations (second release) | Operation tests pass; `stylebook-api` candidate routes unchanged |
| E | API: undo routes and run-history polish (second release) | Reverting a recorded run restores before-state; the new-year run follows |
| F | Optional interface over the run record | Only after the format has held across several runs |

Phase A can start independently of everything else. Phase D can begin against a local instance as
soon as phase B exists.

## Validation

API validation (operation, guard-parity, read-parity, envelope, undo, and preview tests) is in the
[API plan](stylebook-cleanup-api.md#validation). Backfield tests the surface; the toolkit tests its
own cleanups. For the toolkit and prevention:

- Engine unit tests for consensus, hard vetoes after readers, the transitive component-conflict
  check, and the closure loop, built from the cases logged in the case studies.
- Recorded-decision tests: feed recorded 2024 evidence packets and reader outputs through the engine
  and compare the plans with what was applied (no model calls). A second pass on the result must
  propose almost nothing. There is no full-year dump replay; the new-year run is the live check,
  against the toolkit's own pass bar (see "Patterns every skill follows").
- Contract test: the toolkit fails cleanly against an instance missing a capability or running an
  unknown preview version.
- After ingest serialization: concurrent identical creates produce one canonical.
- Run `make lint`, `make test`, and `make smoke` for runtime changes in this repo, per `AGENTS.md`.

## Open questions

API questions (key hardening, rate limits, the reindex adapter, undo depth, capability versioning,
and snippet controls) are in the [API plan](stylebook-cleanup-api.md#open-questions). Toolkit
questions:

1. **One rubric, two consumers.** The in-product "Review with AI" and the toolkit should judge by the
   same rules. Does the toolkit own the rubrics and the product copy them, or does the product
   publish them (the program doc suggested an MCP resource)?
2. **Data egress.** Snippets from an instance go to the toolkit user's model providers. Is an
   acknowledgement in `start-run` enough, or should the instance also be able to restrict snippets
   (see the API plan)?
3. **Incremental runs.** What is the watermark: canonicals created or changed since the last run?
4. **Accounting.** Model cost now lives in the toolkit's run folder, not `backfield_ai_call_record`.
   Does the instance want an optional place to record it?
