# Testing regime

## Layers

1. **Unit (agate-runtime, backfield-auth)**
  Graph execution, node behavior, and wiring; session/service token helpers. Run: `make test-unit` or `uv run pytest packages/backfield-agate/tests packages/backfield-auth/tests`.
2. **Integration / API smoke**
  FastAPI apps mounted via `TestClient` where no Docker is required. Run: `make test-integration`.
3. **Smoke / end-to-end lanes**
  `make up`, then run the smoke lane that matches the change. Fast lanes stay deterministic and narrow; `make smoke` remains the primary Agate-to-Stylebook handoff lane; slower lanes cover worker lifecycle, editorial review, import, and S3 batch paths separately. Put the LLM keys your flow uses (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `AZURE_API_KEY` / `AZURE_API_BASE`, etc.) and optional geocoder keys in repo-root `.env` when running the starter-flow handoff or place-geocode smokes.

## Validation ladder

1. **Fast local gate**
  - `make lint`
  - `make test`
  - When changing `**apps/stylebook-ui`** or `**packages/backfield-ui**`, also run `**make stylebook-ui-build**` (`npm ci` in `**packages/backfield-ui**` then `**apps/stylebook-ui**`, then `tsc` + `vite build`).
2. **Structural checks**
  Runtime contract and schema-prefix assertions live in the test suite and run as part of `make test`.
3. **Smoke suite**
  Use one of these lanes after `make up`:
  - `make smoke-auth`: session login, `GET /v1/auth/me`, `GET /v1/me/workspaces`, Agate `GET /projects`, and Stylebook permissions all agree on the same user scope.
  - `make smoke-agate-basic`: creates a tiny `TextInput -> Output` graph, runs it through Agate + worker, and asserts the deterministic `json_output.consolidated.text` result.
  - `make smoke-stylebook-basic`: creates a canonical through the Stylebook write API, fetches it back, and asserts the new card starts with `linked_substrate_count == 0`.
  - `make smoke`: the Agate-to-Stylebook handoff lane (`[tests/smoke/golden_path_stack.py](../tests/smoke/golden_path_stack.py)`). In session mode it follows **log in → workspace → project → run**; otherwise it uses the service Bearer path. It asserts the **Starter flow** still matches bootstrap, the run returns `stylebook_output.success == true`, and the persisted article/location is visible through downstream Stylebook read APIs.
  - `make smoke-worker-async`: focuses on run lifecycle (`pending` to terminal state) and the whole-run item detail route.
  - `make smoke-stylebook-editorial`: seeds one pending review candidate, checks queue/context/suggestions, then links it to an existing canonical and verifies the queue and linked-substrate state update.
  - `make smoke-stylebook-import-export`: exercises the GeoJSON analyze + import path with a one-feature fixture.
  - `make smoke-s3-batch`: runs the worker S3 batch setup path with a deterministic fake S3 client and eager Celery execution, then asserts parent and item summaries.
  - `make smoke-place-geocode`: optional in-process PlaceExtract + GeocodeAgent corpus smoke (not part of CI).
  - `make smoke-place-geocode-stack`: optional single-run stack harness for the geocode starter path.
  - `make smoke-people`: optional in-process PersonExtract + DBOutput smoke with mocked LLM (not part of CI).
  - `make smoke-people-stack`: optional stack harness for the **People starter** graph (`starter_people_flow_graph_spec`).
  - **Guided flow builder (manual):** on a live stack, walk through create → parallel branch → edit bookend clear-middle → run from read-only view: `/flow/new` with Text Input → Place Extract → Geocode → JSON Output; add a parallel Place Extract branch from input; save; open `/flow/:id/edit`, change output type with middle steps present (confirm clear); open `/flow/:id`, **Run flow** without **Edit flow**, then **Edit flow** and confirm **+** / delete unlock. See `docs/FRONTEND.md` → **Guided flow builder**.
  Aggregate bundles:
  - `make smoke-fast`: `smoke-auth`, `smoke-agate-basic`, `smoke-stylebook-basic`
  - `make smoke-runtime`: `make smoke`, `make smoke-worker-async`
  - `make smoke-slower`: `make smoke-stylebook-editorial`, `make smoke-stylebook-import-export`, `make smoke-s3-batch`
  Shared knobs: `SMOKE_EMAIL`, `SMOKE_PASSWORD`, `SMOKE_WORKSPACE_SLUG`, `SMOKE_PROJECT_SLUG`, `SMOKE_POLL_TIMEOUT_SECONDS`, `SMOKE_POLL_INTERVAL_SECONDS`. DB-writing live lanes clean up their temporary graphs, runs, canonicals, and substrate rows by default; set `SMOKE_KEEP_DATA=1` when you want to inspect the artifacts after a smoke run. `SMOKE_BOOTSTRAP=1` still creates the first Core user for empty local DBs before the handoff smoke logs in.
4. **Manual UI pass**
   Use the Agate UI when the task changes browser-facing behavior or flowbuilder interactions.

   **Processed item — story text and places (Issue 6):** open a completed run item that has **story text** and **model places** with `original_text` (or span hints) present in the saved output. Click each place row: the story pane should **scroll to a highlighted passage** when a match exists, and show a short **no matching passage** note when it does not—without highlighting arbitrary text. Hover a row briefly to confirm highlight follows the pointer, then move away and confirm the **selected** row still drives the highlight. Rows in the model **`places.needs_review`** bucket (or with geometry cleared in review) should appear in the geocoded-places table with a **No geography** source pill; selecting one should offer **Edit** → **Add point** / **Add rectangle** like a cleared-geometry row, and after assigning geometry the pill should show **Manual**. For parity with the legacy dashboard, spot-check the same item in **agate-ai-platform** `dashboard-ui` if you have a comparable article view.

   **Processed item — catalog handoff (Issue 7):** With unsaved map or description edits on the Review card, choose **Open catalog**: you should be prompted to **save first** (no new tab until save succeeds). After save (or when already clean), Stylebook should open in a new tab with the right **catalog slug** and **project** query when the project’s workspace has a linked catalog. With a **linked** place selected, confirm the tab targets that place’s **canonical detail** when an id is present; otherwise confirm the **canonical list** opens with a reasonable search hint.

## Conventions

- Keep the **starter geocode pipeline** (TextInput → PlaceExtract → GeocodeAgent → Backfield Output / `DBOutput`, no JSON Output node) as the canonical regression story; add tests when changing execution or handles.
- Places reconciliation policy changes should include focused worker tests for **Add Only**, **Smart Merge**, and **Replace** before relying on smoke tests. Cover stale machine-place removal, editor-touched place preservation, hard replacement cleanup, and the no-tombstone behavior for future re-adds.
- Prefer a few high-signal tests over broad shallow coverage.
- When adding nodes, add a focused unit test under `packages/backfield-agate/tests/`.
- When changing API or worker contracts, add or update a test that guards the naming, queue, status, or schema assumption.

### Root `tests/` layout

- **Packages:** unit and tight library tests live under `packages/*/tests/` (for example `packages/backfield-agate/tests/`).
- **Repo root `tests/`:** integration and contract tests, grouped by surface so the tree stays navigable:
  - `tests/core_api/` — `core-api` HTTP tests and core-api-only bootstrap/env behavior.
  - `tests/agate_api/` — Agate API `TestClient` tests.
  - `tests/stylebook_api/` — Stylebook API tests (`stylebook_api` app). `**POST /v1/geocode/resolve`** requires auth (service Bearer, session, or `bfk_`), matching production `resolve_auth` behavior. Substrate ↔ canonical editorial routes (`**GET /v1/candidates/{id}/suggested-canonicals**`, `**POST /v1/locations/{id}/link-canonical**`, `**POST /v1/locations/{id}/unlink-canonical**`, `**GET /v1/canonical-locations/{id}/linked-substrates**`) are covered here as well.
  - `tests/stylebook/` — Stylebook-domain pure tests (for example canonical fuzzy-match scoring without Postgres). **Trigram retrieval** against a live Postgres DB is covered by running `**make migrate`** on Compose and exercising ingest/worker paths locally; CI SQLite runs use the dialect fallback only.
  - `tests/contracts/` — cross-cutting structural checks (schema prefixes, indexes, shared runtime contracts) that are not tied to a single HTTP app.
  - `tests/smoke/` — smoke harnesses and shared helpers. Most lanes run against the live stack (`smoke_auth.py`, `smoke_agate_basic.py`, `golden_path_stack.py`, `smoke_stylebook_basic.py`, `smoke_worker_async.py`, `smoke_stylebook_editorial.py`, `smoke_stylebook_import_export.py`); `smoke_s3_batch.py` is an in-process worker-path harness; `place_geocode_smoke.py` and `smoke_people_stack.py` remain optional extract-path corpus runners. These scripts are invoked via `make`, not pytest collection.
- Shared pytest defaults for these tests live in `tests/conftest.py` at the repo `tests/` root.
- Add new FastAPI integration tests under the folder that matches the app; add new structural or schema-wide assertions under `tests/contracts/`.

## CI suggestion

```bash
uv sync
make lint
make test
```

The GitHub Actions **smoke** job brings up Compose (including `**core-api`**), waits for Core + Agate + Stylebook health, bootstraps a fixed CI user when the DB is empty, sets `**SMOKE_EMAIL` / `SMOKE_PASSWORD**`, then runs the fast smoke bundle plus the session-shaped handoff lane. A separate **smoke-extended** job runs on pushes to `main` and covers `smoke-worker-async`, `smoke-stylebook-editorial`, `smoke-stylebook-import-export`, and `smoke-s3-batch`.

Configure at least one LLM credential your starter-flow handoff needs (`**OPENAI_API_KEY**`, `**ANTHROPIC_API_KEY**`, `**GEMINI_API_KEY**`, `**OPENROUTER_API_KEY**`, or Azure `**AZURE_API_KEY**` + `**AZURE_API_BASE**`) as a [repository secret](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions); optionally add `**MAPBOX_API_TOKEN**`. The workflow writes a short-lived repo-root `.env` so `agate-api` / `worker` receive keys (same mechanism as local dev). Fork PRs from outside contributors typically cannot read those secrets, so the handoff lane may be skipped or failed by policy.