# Stylebook cleanup API: execution plan (draft)

**Status:** Draft, 2026-11-23. Planning only. Turns the design in
[`stylebook-cleanup-api.md`](stylebook-cleanup-api.md) into ordered work. Decision numbers (D29 and
D34-D45) refer to that document. Phases 0 and A are detailed enough to start; B and C are outlined
and get a detailed task list when they begin; C2 and E are sketches.

## Goal

Give outside cleanup tools a keyed, preview API: reads good enough to find problems, operations
that do what a person does by hand (and keep the data correct), and instance protections. Judgment,
phases, review, and completeness checks stay in the cleanup tool.

## Delivery rules

- One branch and one pull request per phase (D44), each cut from `main`, leaving the repo working.
  Do not stack phases on one branch. Branch names are suggestions.
- Before each PR: run `make lint` and `make test`; run `make smoke` for runtime changes (every
  phase here except pure docs); run the pre-PR code and architecture review skills; update the docs
  named in each phase (use the `update-repo-docs` skill).
- DB changes (phase C and the dismissal change in slice 2) use the `backfield-db-change` skill and
  the migration flow in `docs/development/testing.md`.
- Frontend changes (phase 0) follow `docs/development/frontend/conventions.md`: copy for a
  non-technical user.
- Release 1 is phases 0, A, B, C. Release 2 is C2 and E (D43).

## Phase 0: scopes and preview scaffolding

**Branch:** `feat/cleanup-api-scopes`. **Size:** small.

| # | Task | Where |
|---|---|---|
| 0.1 | Add `SCOPE_CLEANUP_READ = "cleanup:read"` and `SCOPE_CLEANUP_APPLY = "cleanup:apply"` to `ALL_SCOPES`; confirm `parse_scopes` and key resolution accept them | `packages/backfield-auth/src/backfield_auth/gate.py` |
| 0.2 | Extend `CredentialScope` and `_normalize_requested_scopes`: `cleanup:read` on any key, `cleanup:apply` on service keys only (same error style as `runs:trigger`). Confirm that creating a service key already requires an organization admin, and that the apply scope inherits that | `apps/core-api/src/core_api/routers/credentials.py` |
| 0.3 | Add a `require_cleanup_scope` dependency (reads and applies) next to the existing scope checks, and a Stylebook-in-organization check for the path's `stylebook_slug` | `apps/core-api/src/core_api/routers/public/cleanup/deps.py` |
| 0.4 | Create the `cleanup` router tagged `cleanup-preview`, mounted in `routers/public/__init__.py`, with a minimal `GET …/cleanup/capabilities` (contract version, key scopes, whether it can apply). This is the one route phase 0 needs to prove scopes and hiding | `apps/core-api/src/core_api/routers/public/cleanup/` |
| 0.5 | Make `build_public_openapi` drop operations tagged `cleanup-preview` (and any path left empty). Filter on the tag, not the path. Keep the routes in the app's own `/openapi.json` | `apps/core-api/src/core_api/routers/public/openapi.py` |
| 0.6 | Agate UI key panel: add both scopes to `PROJECT_API_KEY_SCOPE_OPTIONS` with plain-language labels, `cleanup:apply` as service-only, and generalize `scopesForCreateRequest` and `normalizeScopeSelectionForType` (today they only know `runs:trigger`) | `apps/agate-ui/src/lib/projectApiKeyScopes.ts`, `ProjectAccessKeysPanel.tsx`, and the existing `.test.ts` |
| 0.7 | Docs: a preview section in `docs/api/public.md`; one sentence in `AGENTS.md` and `docs/api/public.md` that preview routes are exempt from the Playground rule until they graduate; list the new scopes wherever `runs:trigger` is documented (`rg "runs:trigger" docs`) | `docs/api/public.md`, `AGENTS.md` |

**Tests (new or extended):**
- `tests/core_api/test_api_key_scopes.py`: user key cannot receive `cleanup:apply`; service key can; unknown scopes still rejected; `read` is always included.
- A new cleanup deps test: a key without the scope gets 403; a key for another organization's Stylebook is rejected.
- OpenAPI test: neither `build_public_openapi` output nor the committed `docs/api/public.openapi.json` contains a cleanup path; the app's internal `/openapi.json` does.
- Agate UI scope-helper tests updated for the new scopes.

**Validation:** `make lint`, `make test`, agate-ui test and build, `make smoke` (a new router is mounted).

**Gate:** both scopes mintable on the right key types and visible in the key panel; the stub route
works with a scoped key; the public contract is unchanged (`docs/api/public.openapi.json` has no diff).

**Risks:** the key panel assumes one optional scope (small refactor); the public OpenAPI test must
fail loudly if a future route is mis-tagged.

## Phase A: shared merge fixes and one apply path

**Branch:** `feat/cleanup-shared-merge`, cut from `feat/stylebook-agent-tooling` (not `main`): that
branch holds the person and organization merge work this phase audits, and is not merged yet.
**Size:** medium. Benefits the Stylebook UI first.

**Status (2026-11-23):** A.1 to A.7 done on the branch; see the shared merge fixes in the API plan
for the per-fix result. People and organizations already satisfied most fixes; the location merge
needed fixes 1, 2, 3, 8, and 9. Differences from the task text: fix 3 reports the unused source
geometry and accepts `geometry_winner` instead of refusing, and `run_id` and `provenance` live in
the activity payload (A.6). The AI-review merge path also moved onto `apply_merge`.

Evidence from the code, which shapes the tasks: `merge_location_canonical_into` already seeds the
source label as an alias, already rewires connections, and already copies the source geometry when
the target has none. So several of the nine fixes in the design are partly done. The activity write
(`backfield_entities/activity.py`) already lives in the library, but the UI routes write it, and
queue reindex, themselves. Reindex lives in `stylebook_api/semantic_reindex.py`.

| # | Task | Where |
|---|---|---|
| A.1 | **Audit, test first.** For each of the nine merge fixes, and for locations, people, and organizations separately, write a failing test from the logged case (aliases carried, connections stay open, geography and metadata not dropped, people fields carried, mixed-kind guard). Record which fixes already hold. Add fixtures from the cases in the case studies, trimmed | `tests/entities/test_location_merge_guard.py`, `test_person_merge.py`, `test_organization_merge.py`, plus new files |
| A.2 | Fix the merge functions until A.1 passes. Fix the guard `location_merge_pair_blocked` so the 169 mixed-kind pairs are refused (finding F10) | `entities/{location,person,organization}/merge.py`, `entities/location/link_identity.py` |
| A.3 | Add the shared apply function `apply_merge` for all three entity types: runs the merge, writes the activity row (actor type and ids are parameters, plus run id and provenance), emits canonical events, and calls an injected reindex callback. No Celery import in the library | `packages/backfield-entities/src/backfield_entities/cleanup/apply_merge.py` |
| A.4 | Refactor the three UI merge routes to call `apply_merge`, keeping their request and response shapes and their 404 and 400 mapping. Pass `enqueue_semantic_reindex_for_entity` as the callback | `apps/stylebook-api/.../routers/stylebook_cleanup.py` (the three `merge-into` routes) |
| A.5 | Decide the reindex adapter for `core-api` (needed in phase C): read `semantic_reindex.py` and `core_api/run_enqueue.py`, then choose one shared module or two thin adapters, and record it in the API plan's open question | docs only, plus a small spike if needed |
| A.6 | Activity row accepts actor type, run id, and provenance without breaking existing readers | `backfield_entities/activity.py` and its tests |
| A.7 | Docs: update the API plan (mark fixes 1-4, 5, 6, 8, 9 done; **move fix 7, persisting `merged_into`, to phase C slice 1**, because it needs the new table), the case-study doc's status lines, and `docs/architecture/overview.md` if a new package module changes dependency direction | `docs/plan/*`, `docs/architecture/overview.md` |

**Validation:** `make lint`, `make test`, `make smoke`. Manual: merge one pair of each type in the
Stylebook UI on a local stack and compare with the previous behavior (aliases, connections, activity
row, reindex job queued).

**Gate:** all A.1 tests pass; UI behavior is unchanged except for the documented fixes.

**Risks:** the fixes change merge results that people rely on, so each one needs a note in the PR;
the refactor touches three routes at once, so keep the diff to "move code, no new behavior" apart
from A.2.

## Phase B: reads

**Branch:** `feat/cleanup-api-reads`. **Size:** large. Detail the task list when A is merged.

Order:
1. **Schemas first.** Pydantic models for every read response (strict types, no loose dicts), the shared cursor and error shape, and the operation-class names used later by ceilings.
2. **Date filter spike.** Run `EXPLAIN ANALYZE` on the mention-to-article-to-canonical join with `substrate_article.pub_date` on realistic data; add an index only if the plan needs one (new indexes use the db-change skill).
3. `capabilities` filled in (entities, checks, ceilings, operator repairs needed).
4. `export` with `updated_since` and `mentioned_from` / `mentioned_to`, built on the shared helpers in `public/*/list_search`.
5. `evidence` (single and batch), `compare`, built on `public/mention_evidence.py` and `canonical_display.py`, with project tags and the **snippet controls** setting (D45).
6. `checks` list, results, run, and latest run over `quality/check_runs.py`.
7. `candidates` list, count, types, and candidate evidence. **Risk:** this logic lives in `stylebook-api` routers today, so extract only the listing and evidence functions into a library here, and leave decisions to C2.
8. `dismissals` list and `integrity` report (the runbook's baseline checks as read-only queries).
9. The keyed `cleanup/openapi.json`, an export script and committed `docs/api/cleanup.openapi.json`, the export route's rate-limit bucket, and `docs/api/cleanup.md` (prose, preview status, how a tool reads the surface).

**Tests:** read-parity tests against the Stylebook UI numbers; date-filter correctness; scope
(project versus Stylebook) behavior from D41; snippet cap and off switch; preview-hiding tests still
pass; schema export is deterministic.

**Gate:** read-parity and date-filter tests pass; the keyed schema lists every read route and no
apply route exists yet.

**Risks:** export cost on large instances; evidence responses carrying more text than expected
(controlled by D45); the candidate extraction.

## Phase C: apply surface, release 1

**Branch:** `feat/cleanup-api-apply`. **Size:** large; ordered by slice, one commit group each. If
review becomes unwieldy, split at a slice boundary (D44 allows it).

**Slice 1: runs, ledger, merges**
1. Write the **before-state spec** (what each operation records so undo works) as a short design note before any code.
2. Migration and models, `stylebook_` prefix: `stylebook_cleanup_run`, `stylebook_cleanup_action`, `stylebook_canonical_redirect`; indexes per the API plan.
3. Library: `envelope`, `ceilings` (settings with defaults sized from the 2024 counts, smaller for retirements and deletions), `ledger` (same transaction, fail closed), `runs`.
4. Routes: open and close runs, `merges`, run and action reads, `resolution`. Persist `merged_into` inside `apply_merge`.
5. The `core-api` reindex adapter chosen in A.5; activity actor `agent`, credential id and label recorded.

**Slice 2: edits, aliases, dismissals**
- `edits` over `geometry_apply.py` and the per-type `persist.py`; `aliases` over `editorial_aliases.py`.
- `dismissals`: today they lack a reason, are Stylebook-wide, and cannot be listed or reopened (finding F11). This needs a migration for reason code and run id, a reopen path, and keeping the UI routes working.

**Slice 3: retirements and deletions**
- Extract the organization retirement pattern and the people removal pattern from the hand-cleanup scripts in `tmp/stylebook-agent-cleanup/` into library functions with `mention_disposition` and per-mention reason codes in one transaction. Note the UI's delete route refuses when linked mentions exist, which is exactly the `refuse` default, so UI behavior stays the same.

**Tests per slice:** operation tests from the logged cases; guard parity with the UI; `dry_run`
mutates nothing; ceilings return `ceiling_reached`; aborted run rejects applies; ledger failure fails
the item; one failing item rolls back alone; `merged_into` resolution; `refuse`, `waive`, and
`requeue` behavior; hard deletions emit the deleted event and close connections.

**Validation:** `make lint`, `make test`, migration flow, and **extend `make smoke`** (or its
backing script) with a small cleanup scenario: open a run, dry-run then apply one merge, read the
ledger. The golden path smoke has no cleanup coverage today.

**Gate:** operation tests for all three slices pass; UI routes still behave the same; the smoke
scenario passes on a live stack.

**Risks:** the migration (new tables only, low risk); ledger growth (before-state JSON size);
reindex volume for big runs; a service key can change any Stylebook in its organization (accepted in
D35, tracked in the open questions).

## Phase C2: candidate decisions, mention links, relations (release 2)

**Branch:** `feat/cleanup-api-candidates`. **Size:** large. Sketch:
- Move the candidate decision logic from `stylebook-api` `entities/*/candidates.py` into a library, then point both the UI routes and the new `decisions` route at it.
- Add `mention-links` over `entities/linking/substrate_actions.py` and `relations` over `connections/writer.py`.
- Biggest risk: the extraction, since the candidate queues are heavily used in the UI. Land the extraction with UI behavior unchanged first.

## Phase E: undo and run history (release 2)

**Branch:** `feat/cleanup-api-undo`. **Size:** medium to large. Sketch:
- Undo for every operation except hard deletions (D43), from the before-state spec, per action and per run; refuse a deletion undo with a clear reason.
- Run-history polish on the routes added in C.
- Tests: apply then undo restores the recorded state for each operation; undo of a partly changed state fails clearly.

## Cross-cutting

- **Docs to keep current:** the API plan, program decision log, `docs/api/cleanup.md` (B on), `docs/README.md` entries, and `docs/OBSERVABILITY.md` if cleanup operations get metrics (open question 9).
- **Out of scope here:** the cleanup toolkit repository, rubrics, review flow, and any tool-side validation; the general guidance statement for tools (written after the surface exists); key expiry and Stylebook binding.
- **Preview graduation** (Playground entries, public OpenAPI) happens only after several real runs and a second consumer, not in these phases.

## Open items to resolve inside the phases

| Item | Resolved in |
|---|---|
| Reindex adapter (shared module or two adapters) | A.5 |
| Before-state format and how much of a merge revert is automatic | C slice 1, task 1 |
| Ceiling values and storage (settings) | C slice 1, task 3 |
| Date-filter index need | B, step 2 |
| Export rate-limit bucket | B, step 9 |
| Snippet setting shape (global cap versus per key) | B, step 5 |
| Candidate extraction boundary between B and C2 | B, step 7 |
