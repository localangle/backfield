# Stylebook cleanup API (planning)

**Status:** Planning. Nothing here is a runtime contract. Split out of
[`stylebook-cleanup-toolkit.md`](stylebook-cleanup-toolkit.md) on 2026-11-23; narrowed the same day
to a surface for external tools, with no opinion about how they run a cleanup.

This is the plan for the keyed API in this repository that external cleanup tools call: who may
call it, which operations and reads exist, where they live in the code, and how the surface
launches as a preview. The outside cleanup toolkit is the first consumer. It lives in its own
repository and owns everything about how a cleanup is carried out.

Related documents:

- [`stylebook-cleanup-toolkit.md`](stylebook-cleanup-toolkit.md): the design for the first consumer
  (skills, engine, rubrics, run artifacts) plus Backfield's ingest-prevention and operator-repair
  work. Its principles about the API still hold: the API is the only write path for the toolkit, the
  API is model-free, and the server never acts on its own.
- [`stylebook-maintenance-program.md`](stylebook-maintenance-program.md): the decision log. This plan
  fills in spec D (agent API, auth, and undo).
- [`stylebook-agent-maintenance.md`](stylebook-agent-maintenance.md): the first endpoint sketch,
  which this plan supersedes, and the merge-semantics findings behind the shared merge fixes.
- [`stylebook-maintenance-job-catalog.md`](stylebook-maintenance-job-catalog.md): the jobs the
  operations support.

## What Backfield owns, and what it does not

Backfield provides a **surface**: operations an automated tool can call, reads good enough to find
problems, and protections for the instance. It is unopinionated about how a tool uses them.

The test for any rule: *would the Stylebook UI need it too?* If so, it belongs here. If it exists
only so that a cleanup run succeeds, it belongs in the toolkit.

| Backfield owns | The toolkit owns |
|---|---|
| The operations (merge, edit, retire, delete, alias, dismiss, relate, relink, candidate decisions, undo) | What to clean, and the order and phases of a run |
| Data-model invariants inside each operation: aliases carried, connections rewired, events emitted, reindex queued, `merged_into` persisted, activity attributed | Judgment: rubrics, reader consensus, vetoes beyond what the UI enforces, the sensitive-type policy |
| The same per-item guards the UI has (fixed once, for both) | Staleness: re-reading before applying a plan that waited |
| Reads: export, evidence, compare, checks, candidates, dismissals, integrity, capabilities | Recall, grouping, and packets built from those reads |
| Instance protections: scopes, rate limits, operator ceilings, a kill switch, `dry_run` default, snippet controls | Its own plan limits, budgets, and cost accounting |
| A before-state ledger and undo for every operation | Whether to review, sample, or revert |
| Stored provenance, reason codes, and run labels, **uninterpreted** | Their meaning and vocabulary |
| Testing that each operation and read does what it says | Testing that a cleanup is complete, correct, and reduces queues as expected |

Backfield has no review state, no plan object, no required order of calls, and no judgment about
whether a request is a good idea beyond what the UI already refuses.

## Decisions recorded here

Also in the program doc's decision log (D29 and D34-D45), alongside the toolkit decisions D30-D33.

| # | Decision |
|---|----------|
| D29 | External tools authenticate with a project API key and call a keyed cleanup namespace under `/public/v1`. The browser-session and service-token cleanup routes stay for the Stylebook UI. |
| D34 | Apply is one route per operation (merges, edits, retirements, deletions, aliases, relations, dismissals, mention links, candidate decisions, undo), all sharing one request and response envelope and one server pipeline. |
| D35 | `cleanup:read` may be granted on any project key. `cleanup:apply` is granted on service keys only, so creating an apply key requires an organization admin (the same rule as `runs:trigger`). |
| D36 | Canonical export is a new cleanup route. It does not extend the public list routes, whose contract is consumer-facing. |
| D37 | Path shape: `/public/v1/projects/{project_slug}/stylebooks/{stylebook_slug}/cleanup/...`. The Stylebook is an explicit path segment, never an implied default. |
| D38 | The cleanup routes launch as a **preview** surface: hosted in `core-api` under `/public/v1`, tagged `cleanup-preview`, excluded from the public OpenAPI (reads are listed in the API Playground as a separate group), and documented in prose and in a keyed schema. See [Preview status](#preview-status). |
| D39 | Backfield provides operations, reads, and instance protections. It is unopinionated about how tools use them. Per item, the API enforces what the UI enforces and the data-model invariants of each operation; judgment and completeness belong to the tool. There are no fingerprints, idempotency keys, per-item integrity snapshots, review state, or plan objects on the server. |
| D40 | The API mimics hand cleanup. Removal is two operations: **retirements** (soft: the canonical becomes inactive) and **deletions** (hard: the canonical is removed). Both take a `mention_disposition` (`refuse`, the default, `waive`, or `requeue`) and a reason code per affected mention, all in one transaction. With `refuse`, a canonical that still has live mentions is not retired or deleted. |
| D41 | Project scope: candidate queues are project-scoped by default (optional `scope=stylebook`); evidence is Stylebook-wide with a project tag on each item; service keys see the Stylebook-wide view. |
| D42 | A **run** is a lightweight grouping the caller opens when it chooses (label, `client_run_ref`, credential). It exists for attribution, the ledger, and undo. There is no lease, declared cap, or expiry. Instance protection is operator-set **ceilings** per operation class per run, plus a kill switch. Reason codes and provenance are stored as given and never interpreted. |
| D43 | The first release is phases 0, A, B, and C (reads, and apply for merges, edits, aliases, dismissals, retirements, and deletions). Candidate decisions, mention links, relations (C2), and undo (E) are a second release. Undo covers every operation except **hard deletions**, which are recorded in the ledger with their before-state but have no undo route. |
| D44 | Delivery is one branch and pull request per phase, each leaving the repository working, with the pre-PR code and architecture reviews. |
| D45 | The first release includes basic snippet controls: an instance setting that caps snippet length or turns snippets off in evidence responses. |

## Credentials

Today a project API key (`bfk_...`, hashed, revocable, with `read` and `runs:trigger` scopes) is
accepted only on `/public/v1`. The cleanup routes use the internal resolver, which rejects `bfk_`
keys. Decision D29 puts external tools on a keyed namespace under `/public/v1`, hosted in
`core-api`.

Why `core-api` and not `stylebook-api`:

- `core-api` is the only externally documented service (`api.{organization_slug}.backfield.news`);
  `stylebook-api` is internal and proxied by the UIs.
- Key authentication, per-project rate limiting, and the OpenAPI machinery live in
  `core_api/routers/public/` (`deps.py`, `rate_limit.py`, `openapi.py`).
- `stylebook-api` denies keys on purpose (`can_edit_stylebook` returns `False` for an API key).
- `core-api` already publishes Celery tasks (`run_enqueue.py`), so it can queue semantic reindex.

Scopes and access:

| Scope | Granted to | Allows |
|---|---|---|
| `cleanup:read` | Any project key (user or service) | Every read route |
| `cleanup:apply` | **Service keys only** (D35) | Every apply route, including `dry_run` requests |

- Add both scopes to `ALL_SCOPES` in `backfield_auth/gate.py`, and accept them in
  `core_api/routers/credentials.py`, which already restricts `runs:trigger` to service keys created
  by an organization admin. Reject `cleanup:apply` on user keys the same way.
- A key reaches the Stylebook named in the path, which must belong to the key's organization. A
  project key can already read other Stylebooks in its organization through the existing optional
  `stylebook_slug` query, so reads add no new exposure. Writes are limited by who can mint a
  service key.
- Service keys have no user. Every apply therefore records the credential id and its label in the
  ledger and activity payload, plus the run id and the caller's provenance (stored as given). The
  activity actor type is `agent`. Name keys after the person or tool that holds them.
- The ledger write must be in the same transaction as the change and fail closed. Activity writes
  can stay best-effort (`log_stylebook_activity_safe` swallows errors, so it must not carry the
  ledger).

### Project scope (D41)

A Stylebook belongs to an organization and can serve several projects, while a key belongs to one
project. Cleanup follows these rules:

- **Queues** (candidates, check results) are limited to the key's project by default. Pass
  `scope=stylebook` to see every project's queue. Service keys may use either.
- **Evidence** is Stylebook-wide, because a merge affects every project's mentions. Each evidence
  item carries a project tag so a tool can tell whose article it is.
- **Date filters** (below) apply on top of scope.

## Route catalog

A tool with no database access must be able to build its own view from reads. A bulk export of
canonicals is small (about 20,000 place canonicals fit in a few megabytes), so a tool can compute
groupings itself and fetch snippets only for the groups it needs.

**Base path** (D37):
`/public/v1/projects/{project_slug}/stylebooks/{stylebook_slug}/cleanup`, written `…/cleanup` below.
`{entity}` is `locations`, `people`, or `organizations`, matching the existing public routes.
Phase letters refer to [Phasing](#phasing).

**Date filters.** Export, check results, and candidate reads accept `mentioned_from` and
`mentioned_to` (article publication dates, from `substrate_article.pub_date`, which is indexed). They
are general read filters. Cleaning one year at a time is a tool's choice, not an API concept.

### Reads (`cleanup:read`)

| Route | Purpose | Built on | Phase |
|---|---|---|---|
| `GET …/cleanup/capabilities` | Preview contract version, entities, checks with algorithm versions, supported operations, ceilings, the key's scopes, whether it can apply, operator repairs needed | New | B |
| `GET …/cleanup/openapi.json` | The keyed cleanup contract (see [Preview status](#preview-status)) | New builder alongside `routers/public/openapi.py` | B |
| `GET …/cleanup/{entity}/export` | Cursor-paginated canonical export with `updated_since` and the date filters: label, kind, status, address, point, shape summary, mention count, alias summary, timestamps | New; shares query helpers with `public/*/list_search` | B |
| `GET …/cleanup/{entity}/{id}/evidence` | Full evidence package: aliases with provenance, metadata, connections, activity, geography of linked mentions, snippets with article references and project tags | New assembler over `public/mention_evidence.py`, `public/canonical_display.py`, `entities/*/review.py` | B |
| `POST …/cleanup/{entity}/evidence` | Same, for a batch of ids (POST only because of the id list; still read-only) | Same | B |
| `GET …/cleanup/{entity}/{id}/compare/{other_id}` | Evidence for any pair, including pairs no check surfaced | Same | B |
| `GET …/cleanup/checks` | Check ids and algorithm versions | `quality/checks.py` | B |
| `GET …/cleanup/checks/{check_id}/results` | Cached results with reasons and watermarks | `query_cached_check_results` in `quality/check_runs.py` | B |
| `POST …/cleanup/checks/{check_id}/runs` | Start a check run | `quality/check_runs.py` | B |
| `GET …/cleanup/checks/{check_id}/runs/latest` | Latest run status | Same | B |
| `GET …/cleanup/candidates/{entity}` | Candidate queue; also `/count` and `/types` | Wraps what `stylebook-api` `routers/stylebook_candidates.py` lists today | B |
| `GET …/cleanup/candidates/{entity}/{id}/evidence` | Article context and ranked catalog matches | `canonical/candidate_review.py`, `catalog/candidate_ai_review.py` | B |
| `GET …/cleanup/dismissals` | Dismissals with reason, actor, and run | New read over the dismissal table | B |
| `GET …/cleanup/{entity}/integrity` | Read-only report on the data model's own invariants: dangling references, invalid link states, cross-Stylebook references, open connections on inactive canonicals, counts. What to do with it is the caller's business | New; the runbook's baseline checks | B |
| `GET …/cleanup/{entity}/{id}/resolution` | `merged_into` lookup for an old id | New table | C |
| `GET …/cleanup/runs`, `…/runs/{run_id}`, `…/runs/{run_id}/actions` | Run history and the action ledger | New tables | C |

Mention listing needs no new route. The existing public `/projects/{p}/locations/{id}/mentions`
family covers it.

### Apply (`cleanup:apply`, D34, D35)

One route per operation, all using the envelope below.

| Route | Operation | Built on | Phase |
|---|---|---|---|
| `POST …/cleanup/runs`, `…/runs/{run_id}/close` | Open a run, or close or abort it (D42) | New | C |
| `POST …/cleanup/{entity}/merges` | Merge sources into a survivor, with optional field-level choices (label, kind, geography). Carries every alias and the source label as trusted aliases, rewires connections before pruning, never drops geography or metadata silently | `entities/{location,person,organization}/merge.py` | C |
| `POST …/cleanup/{entity}/edits` | Kind, label, type, district keys, shape (set or clear), optionally pushing the shape to mentions | `entities/location/geometry_apply.py`, per-type `persist.py` | C |
| `POST …/cleanup/{entity}/retirements` | Soft-retire a canonical (status becomes inactive). `mention_disposition` applies (D40) | The organization retirement pattern from hand cleanup, moved into `entities/*` | C |
| `POST …/cleanup/{entity}/deletions` | Hard-delete a canonical: waive or requeue linked mentions with a reason code, queue reindex, record the deleted event, close open connections, delete. `mention_disposition` applies (D40) | `entities/location/delete.py` and the people and organization equivalents | C |
| `POST …/cleanup/{entity}/aliases` | Add or remove aliases with provenance | `canonical/editorial_aliases.py` | C |
| `POST …/cleanup/dismissals` | Dismiss or reopen, with a reason code stored as given; per pair or per canonical issue | `quality/dismissals.py` | C |
| `POST …/cleanup/{entity}/relations` | Record `related_but_distinct` as a connection so a hierarchy pair stops resurfacing | `connections/writer.py` | C |
| `POST …/cleanup/{entity}/mention-links` | Link, unlink, or relink a mention | `entities/linking/substrate_actions.py` | C |
| `POST …/cleanup/candidates/{entity}/decisions` | Link, create, waive, or hold, with reason codes | Candidate logic now in `stylebook-api` `entities/*/candidates.py`, moved into a library | C |
| `POST …/cleanup/actions/{action_id}/undo`, `…/runs/{run_id}/undo` | Revert from the before-state. Every operation except hard deletions (D43) | New | E |

The operation set follows what the stylebook UI and the hand cleanups already do, so that nothing a
person does by hand requires SQL. Which operations a given tool needs is the tool's finding to
report (the toolkit calls these `tooling_gap`s).

### Envelope

Shared by every apply route:

- Request: `run_id`, `dry_run` (default `true`), and a list of items. Each item has a client item
  id, the operation payload, and optional provenance (stored as given).
- Response: per item, a status (`would_apply`, `applied`, `noop`, or `error`), a reason code, an
  action id, and whether reindex was queued.
- Server pipeline for every item: check scope and Stylebook access, check the run is open and under
  its ceilings, run the guards the UI runs, write the before-state to the ledger, apply in a
  per-item transaction, queue reindex, write the activity row.
- **Retries need no idempotency key.** Persisting `merged_into` makes a repeated merge a `noop`, and
  a retry of any other operation is a `noop` or an `error` the item reports. After a crash, a
  caller reads `runs/{id}/actions`.

### Instance protections

These protect the instance and its owner from any key, whatever tool holds it:

- **Operator ceilings.** Each operation class has a per-run ceiling in server configuration, sized
  for a real yearly run from the 2024 numbers. `retirements` and `deletions` have much smaller
  ceilings because they are the hardest to reverse. An item past a ceiling returns `error` with
  reason `ceiling_reached`. An operator can raise a ceiling without a deploy. A tool's own plan
  limits are its business.
- **A kill switch.** Closing a run as aborted stops further applies on it, and revoking the key
  stops everything.
- **`dry_run` defaults to `true`.**
- **A before-state ledger** on every action, written in the same transaction and failing closed. It
  is not a gate. It makes undo possible and records what happened.
- **Rate limits and snippet controls** (see the open questions).

Besides those, the server guarantees:

- per-item transactions with a result for each item;
- semantic reindex queued as part of the operation, or the affected articles returned;
- canonical events emitted, and a persisted `merged_into` record for old ids;
- a scope check on every route.

## Code placement

```text
apps/core-api/src/core_api/routers/public/cleanup/
  __init__.py  deps.py  schemas.py          # deps: scope check and Stylebook-in-organization check
  capabilities.py  openapi.py  export.py  evidence.py  compare.py  checks.py
  candidates.py  dismissals.py  integrity.py  resolution.py  runs.py
  merges.py  edits.py  retirements.py  deletions.py  aliases.py  relations.py
  mention_links.py  candidate_decisions.py  undo.py      # one module per route, as elsewhere

packages/backfield-entities/src/backfield_entities/cleanup/   # new: evidence, export, apply
  envelope.py  ceilings.py  ledger.py  runs.py  evidence.py  export.py  integrity.py
  apply_merge.py  apply_edit.py  apply_retirement.py  apply_deletion.py  apply_alias.py
  apply_relation.py  apply_dismissal.py  apply_mention_link.py  apply_candidate_decision.py  undo.py
# detection and checks stay in backfield_entities/quality/
```

- `routers/public/__init__.py` includes the cleanup router; routers stay thin and call the library.
- `packages/backfield-db`: three new tables with the `stylebook_` prefix and an Alembic migration:
  `stylebook_cleanup_run` (label, `client_run_ref`, status, credential id, timestamps),
  `stylebook_cleanup_action` (ledger, before-state, provenance), and
  `stylebook_canonical_redirect` (`merged_into`). Index the lookups the routes use: actions by run
  and by Stylebook and time, runs by Stylebook and status, and redirects by Stylebook, entity type,
  and old id (unique). Use the `backfield-db-change` skill.
- `packages/backfield-auth`: the two new scopes and a `require_cleanup_scope` dependency.
- `apps/stylebook-api`: the UI routes (`merge-into`, delete, dismissals) are refactored to call the
  same `cleanup/apply_*` functions with actor `user`. Today each router performs the library call,
  the reindex enqueue, and the activity write itself, which is why library-only callers skipped
  reindex and why every activity row said `user`. One shared path fixes both.
- Reindex: the library takes an enqueue callback. `stylebook-api` already has one
  (`semantic_reindex.py`); `core-api` gets a thin equivalent next to `run_enqueue.py`, so the
  library has no Celery dependency.
- Events: merge and delete already emit canonical events through `backfield-events`; the apply
  functions must keep emitting them.
- Per-item transactions: today's router commits once per merge; the batch commits per item and
  reports each result.

## Preview status

The cleanup routes launch as a **preview** surface (D38). The contract is still moving through
phases B-E (envelope, run model, undo), and the public OpenAPI describes itself as a stable
consumer API. Putting batch apply routes in it now would make later changes breaking.

- **Hidden from the public contract.** Tag every cleanup router `cleanup-preview`.
  `build_public_openapi` skips that tag, so the routes stay out of the unauthenticated
  `/public/v1/openapi.json` and the committed `docs/api/public.openapi.json`. Filter on the tag, not the path, so a later path change cannot leak a route. Do not use
  `include_in_schema=False`, which would also drop the routes from the internal `/openapi.json`.
- **Keyed contract for external tools.** `GET …/cleanup/openapi.json` (requires `cleanup:read`)
  serves the cleanup schema, and the export script can write a committed copy such as
  `docs/api/cleanup.openapi.json`. A tool reads it after `capabilities`.
- **Documented in prose.** Add `docs/api/cleanup.md` and link it from `docs/api/public.md` as a
  preview. Hidden from the public contract does not mean undocumented. Later, once the surface is built,
  add a short **general guidance statement** a tool can be given alongside the keyed schema. It
  states facts about the data and the operations (what a merge carries over, what
  `mention_disposition` does, which things are hard to reverse, that snippets are untrusted text,
  and that undo exists). It does not carry judgment. Rubrics and decision policy live in the
  cleanup tool.
- **Same protections as a documented route.** Key authentication, scopes, rate limits, the
  `dry_run` default, and the instance protections above apply unchanged.
- **Playground, reads only (revised).** The first plan kept preview routes out of the Playground
  because it holds keys in browser memory, and a `cleanup:apply` key in a browser tab makes
  accidental applies easy. Reads were later added as a separate "Cleanup (preview)" group so they
  are easy to inspect, loaded from an unkeyed `GET /public/v1/cleanup/openapi.json`. Apply routes
  (runs, merges, and later operations) stay out of the Playground; a new apply route needs no
  Playground work, a new read route needs an entry in `apps/api-playground/src/lib/openapi.ts`.
- **Capability versioning.** `capabilities` returns a preview contract version, and a tool can
  refuse to run against a version it does not know. This stops "undocumented" from becoming
  "unversioned".
- **Graduation.** Move a route into the public contract, and add its Playground presentation (an
  `{entity}` picker and evidence helper text in `apps/api-playground/src/lib/presentation.ts`),
  only after its shape has held across several runs and a second consumer exists. Reads can
  graduate before apply routes because they are harmless.

## Shared merge fixes (the first safety work)

These come from the places and people case studies and benefit the UI immediately. Because the UI
routes move onto the same apply functions, they ship before any keyed route does. Since the API's
per-item guard is the UI's guard (D39), improving it here improves both.

Status after phase A (branch `feat/cleanup-shared-merge`):

1. Rewire connections before relinking mentions, or stop pruning from closing connections the merge
   is about to move. **Done.** People and organizations already held (tests added); locations rewired
   after relinking and now rewire first.
2. Carry all source aliases and the source's own label to the survivor, never overwriting a
   survivor alias, with reviewed-merge provenance. **Done.** People and organizations already held;
   locations carried only the label (and could rewrite a survivor alias) and now match them.
3. Never drop geography or metadata silently. **Done, with a deliberate change from "refuse".**
   Location metadata now moves to the survivor (a conflicting value refuses, as for people and
   organizations). When both locations have geography, the survivor keeps its own unless the caller
   passes `geometry_winner="source"`, and the merge result reports the source geometry it did not
   use. Refusing every both-have-geography merge would block most UI merges, since two records of
   one place rarely share an identical point.
4. Carry `public_figure`, title, and affiliation for people. **Already held** (existing test).
5. Accept actor type, run id, and provenance on the activity row. **Done** through the shared apply
   function: actor type and source are parameters, and `run_id` and `provenance` ride in the row's
   `payload_json`, so no schema change and no reader breaks. A dedicated run column arrives with the
   run table in phase C.
6. Queue semantic reindex inside the shared operation, not only in the API layer. **Done**
   (`apply_merge` takes the enqueue function, so the library has no Celery dependency).
7. Persist `merged_into`. **Done** in phase C, slice 1: `apply_merge` records the redirect, for the
   app's merge routes and the keyed route alike.
8. Remove the redundant delete after pruning. **Done** for locations (the merge deleted a source the
   relink had already pruned, which SQLAlchemy reported as a zero-row delete); people and
   organizations never did it.
9. Close the gaps in the shared merge guard that case studies exposed. **Done.**
   `location_merge_pair_blocked` now refuses any two records with different place kinds, even when
   the labels match (the identity escape hatch allowed 169 of 182 mixed-kind pairs), and the UI error
   already tells the user to fix the kind first. Records with no kind are not blocked. The AI-review
   proposal builder uses the same guard, so it stops proposing such merges.

## Phasing

Phase letters match the phasing table in the toolkit plan; phase D (the toolkit repository) is not
an API phase.

Delivery (D44): one branch and pull request per phase, each leaving the repository working, with
the pre-PR code and architecture reviews. Phase C is internally ordered by slice.

| Phase | Work | Gate |
|---|---|---|
| 0 | Add the `cleanup:read` and `cleanup:apply` scopes and the preview tag filter, with an empty cleanup router in `core-api`. Add the scopes to the project access-key panel in `agate-ui` (`ProjectAccessKeysPanel.tsx`, `projectApiKeyScopes.ts`), with user-facing copy and the service-key-only rule for apply | Scopes mintable on the right key types and visible in the key panel; `cleanup-preview` routes absent from the public OpenAPI |
| A | The shared merge fixes above (except `merged_into`), and the UI merge routes moved onto the shared apply function | Merge tests from the logged cases pass; UI behavior unchanged except for the fixes |
| B | Read routes: capabilities, keyed schema, export with date filters, evidence, compare, checks, candidates, dismissals, integrity, and the basic snippet controls (D45) | Read-parity tests pass; the date filter is fast on a realistic dataset |
| C | Apply surface, slices 1-3: (1) before-state spec, runs, ledger, ceilings, `merged_into`, and merges; (2) edits, aliases, dismissals; (3) retirements and deletions | Operation tests pass for each slice; the UI routes still behave the same |
| C2 | Apply surface, slice 4: relations, mention links, candidate decisions (the candidate logic moves out of `stylebook-api` into a library) | Operation tests pass; the `stylebook-api` candidate routes still behave the same |
| E | Undo routes (D43) and run-history polish | Undo restores the recorded before-state for every undoable operation |

**Release 1** is phases 0, A, B, and C. **Release 2** is phases C2 and E (D43). Release 1 already
lets a tool read everything and apply merges, edits, aliases, dismissals, retirements, and
deletions. Tools that need candidate decisions, mention links, relations, or undo wait for
release 2.

How a tool validates a whole cleanup run (for example, a new year of data) is the tool's concern and
is not a phase gate here.

## Validation

Backfield tests the surface, not the cleanup:

- **Operation tests**, built from the cases logged in the case studies (for example `Brownsville, TN`
  and `TX`, `Kennedy-King College` and `U Building`, and `BP` far apart): connections stay open,
  aliases and label carried, geography never lost, activity attributed, reindex queued, a repeated
  merge is a `noop`, and every merged-away label resolves to the survivor.
- **Retirement and deletion tests:** `refuse` blocks when mentions are live; `waive` and `requeue`
  behave as documented; deletions emit the deleted event and close connections.
- **Guard parity:** the API refuses what the UI refuses, because both call the same function.
- **Read parity:** export, evidence, and queue counts match what the Stylebook UI shows for the same
  scope; the date filter behaves correctly.
- **Envelope and protection tests:** `dry_run` mutates nothing; ceilings return `ceiling_reached`;
  an aborted run rejects applies; one failing item rolls back alone and is reported by item; a
  ledger write failure fails the item.
- **Undo tests:** for each undoable operation, apply then undo restores the recorded before-state;
  an undo request for a hard deletion is refused with a clear reason.
- **Preview tests:** the public OpenAPI and `docs/api/public.openapi.json` contain no
  `cleanup-preview` route; `GET …/cleanup/openapi.json` requires `cleanup:read` and lists them; a
  user key cannot be created with `cleanup:apply`; an apply request without the scope is rejected.
- API Playground updated and checked for every route that graduates into the public contract.
- Run `make lint`, `make test`, and `make smoke` for runtime changes, per `AGENTS.md`.

Whether a cleanup captured everything, and whether queues shrank as expected, is validated by the
tool that ran it.

## Open questions

1. **Before-state format.** **Settled for merges** in
   [`stylebook-cleanup-api-ledger.md`](stylebook-cleanup-api-ledger.md): a pre-image of the rows a
   merge can touch, undone automatically only when those rows are still as the merge left them.
   Each later operation adds its own section there before it is built. Hard deletions record their
   before-state but are not undoable (D43).
2. **Ceilings.** **Settled:** environment settings with defaults (see the ledger note). Original question: where the per-operation ceilings live (environment settings or a small table) and
   their starting values, sized from the 2024 counts, with smaller values for retirements and
   deletions.
3. **Key hardening.** A service key with `cleanup:apply` can change any Stylebook in its
   organization. Settled for now by D35 (organization admins mint these keys). Still open: an
   optional per-key expiry and an optional binding to one Stylebook.
4. **Rate limits.** The public limiter is per project. The export route probably needs a larger
   bucket or a separate limit.
5. **Date filter cost.** Confirm with `EXPLAIN` on realistic data that the join from mention to
   article to canonical is cheap enough for export.
6. **Reindex adapter and volume.** Decided in phase A: two thin adapters. Each app already owns its
   Celery producer (`stylebook-api` `semantic_reindex.py`, `core-api` `run_enqueue.py`, `agate-api`),
   and the shared library supplies only the affected-article scopes and the task name, so a shared
   module would put a queue client in the library. `core-api` has its adapter (built in phase C slice 1; it satisfies `ReindexEntity` in `backfield_entities/cleanup/apply_merge.py`). Still open: whether
   a large run needs throttled enqueueing.
7. **Capability versioning.** The preview contract version in `capabilities` is the starting
   point. Still open: whether features are also advertised individually, so an older instance and a
   newer tool can negotiate partial support.
8. **Snippet controls.** Decided in D45: an instance setting. Still open: the exact setting shape
   (a global cap versus per-key) and whether it also covers the candidate evidence route.
9. **Observability.** Whether `docs/OBSERVABILITY.md` needs metrics for cleanup operations.
