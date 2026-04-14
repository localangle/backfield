# Testing regime

## Layers

1. **Unit (backfield-core, backfield-auth)**
  Graph execution, node behavior, and wiring; session/service token helpers. Run: `make test-unit` or `uv run pytest packages/backfield-core/tests packages/backfield-auth/tests`.
2. **Integration / API smoke**
  FastAPI apps mounted via `TestClient` where no Docker is required. Run: `make test-integration`.
3. **End-to-end (manual or CI)**
  `make up`, then run `make smoke` or open Agate UI and **Run pipeline**. Validates Postgres, Redis, Celery, and the four starter nodes together. `make smoke` runs the **General** project’s **Starter flow** graph (created by local bootstrap on first API start). Put `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` (and optional geocoder keys) in repo-root `.env` so the worker and encrypted project secrets receive them, or the run will fail when those nodes call external APIs.

## Validation ladder

1. **Fast local gate**
  - `make lint`
  - `make test`
2. **Structural checks**
  Runtime contract and schema-prefix assertions live in the test suite and run as part of `make test`.
3. **Golden-path smoke**
  `make smoke` against a live stack. This checks Agate and Stylebook health, finds the seeded **General** project and **Starter flow** graph, enqueues a run, and polls for completion (default poll window allows slow LLM/geocode; override with `SMOKE_POLL_TIMEOUT_SECONDS`). It does not delete General or the starter graph.
4. **Manual UI pass**
  Use the Agate UI when the task changes browser-facing behavior or flowbuilder interactions.

## Conventions

- Keep the **four-node starter pipeline** as the canonical regression story; add tests when changing execution or handles.
- Prefer a few high-signal tests over broad shallow coverage.
- When adding nodes, add a focused unit test under `packages/backfield-core/tests/`.
- When changing API or worker contracts, add or update a test that guards the naming, queue, status, or schema assumption.

## CI suggestion

```bash
uv sync
make lint
make test
```

The GitHub Actions **smoke** job brings up Compose and runs `scripts/smoke_agate_stack.py`. Configure at least one of **`OPENAI_API_KEY`** or **`ANTHROPIC_API_KEY`** as a [repository secret](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions); optionally add **`MAPBOX_API_TOKEN`**. The workflow writes a short-lived repo-root `.env` so `agate-api` / `worker` receive keys (same mechanism as local dev). Fork PRs from outside contributors typically cannot read those secrets, so smoke may be skipped or failed by policy.

**Note:** `make smoke` runs the same script; GNU Make reports **exit code 2** when the recipe fails even if Python exited 1, which can obscure logs in some UIs—prefer invoking `uv run python -u scripts/smoke_agate_stack.py` in automation when you need a clear process exit code.