# Testing regime

## Layers

1. **Unit (backfield-core)**
  Graph execution, node behavior, and wiring. Run: `make test-unit` or `uv run pytest packages/backfield-core/tests`.
2. **Integration / API smoke**
  FastAPI apps mounted via `TestClient` where no Docker is required. Run: `make test-integration`.
3. **End-to-end (manual or CI)**
  `make up`, then run `make smoke` or open Agate UI and **Run pipeline**. Validates Postgres, Redis, Celery, Stylebook geocode, and the four starter nodes together.

## Validation ladder

1. **Fast local gate**
  - `make lint`
  - `make test`
2. **Structural checks**
  Runtime contract and schema-prefix assertions live in the test suite and run as part of `make test`.
3. **Golden-path smoke**
  `make smoke` against a live stack. This checks Agate and Stylebook health, creates a temp project, instantiates the starter template, enqueues a run, and polls for completion.
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

Recommended follow-up job: bring up the runtime stack in CI and run `make smoke`.