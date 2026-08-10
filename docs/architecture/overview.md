# Architecture overview

Backfield is a monorepo with two product surfaces:

- **Agate** builds, runs, and reviews processing flows.
- **Stylebook** manages entity catalogs, candidates, cleanup, activity, and relationships.

Core API exposes authentication, organization administration, AI configuration, and the
consumer-facing `/public/v1` API. All services share Postgres, while Agate run dispatch uses
Redis and Celery.

## Applications

- `apps/agate-api` owns project CRUD, graphs, templates, runs, processed-item review, and node
  metadata HTTP routes. It validates and persists run requests and dispatches worker tasks.
- `apps/worker` owns Celery execution. It loads run context, executes Agate graphs, persists run
  results, writes Backfield Output data, and performs background Stylebook and semantic-indexing
  jobs.
- `apps/stylebook-api` owns editorial Stylebook HTTP behavior: catalogs, canonical entities,
  candidates, cleanup, activity, relationships, and bundle operations.
- `apps/core-api` owns sessions, users, organization administration, project visibility and
  credentials, integration secrets, AI model configuration, and `/public/v1` read and
  run-trigger routes. Interactive project creation and mutation remain in Agate API. Trusted
  offline `backfield organization create` provisioning is the explicit exception: its shared
  database service atomically creates the organization, Stylebook, workspace, project, initial
  memberships, and model snapshot across those domain boundaries.
- `apps/agate-ui` owns the flow builder and run-review experience.
- `apps/stylebook-ui` owns Stylebook catalog, candidate, cleanup, and activity interfaces.
- `apps/api-playground` owns the developer-only schema explorer for `/public/v1`. It derives
  organization API origins at runtime and keeps project API keys only in browser memory.

## Shared packages

- `packages/backfield-agate` publishes the `agate-runtime` Python package. It owns graph types,
  execution, run-trigger helpers, node definitions, node metadata, and node-panel source files.
- `packages/backfield-db` owns SQLModel table definitions, database sessions, encryption helpers,
  seeding, and the single Alembic migration chain.
- `packages/backfield-entities` owns entity registry, catalog resolution, matching and
  canonicalization policy, public entity queries, ingest settings, connections, cleanup, and
  semantic-document synchronization.
- `packages/backfield-ai` owns model resolution, LiteLLM integration, embeddings, and AI call
  accounting.
- `packages/backfield-events` owns event contracts and envelopes, webhook payload signing,
  event-feed cursors, destination (SSRF) validation, transactional run-event recording, and
  delivery claim/terminalize helpers. It stays HTTP-free; transport lives in the worker. See
  [`../development/webhooks.md`](../development/webhooks.md).
- `packages/backfield-auth` owns signed sessions, service authentication, project API-key
  authentication, and shared FastAPI auth dependencies. Internal dependencies accept sessions and
  trusted service tokens; the separate public dependency accepts project keys only on Core API's
  `/public/v1` surface.
- `packages/backfield-observability` owns runtime identity, CloudWatch EMF metric emission, and
  shared lifecycle/external metric helpers. See [`../OBSERVABILITY.md`](../OBSERVABILITY.md).
- `packages/backfield-cli` owns operator commands for stack lifecycle, migration, seeding, and
  data maintenance.
- `packages/backfield-ui` owns shared React components and the output-key helpers used by Agate
  node panels and run views.

Node-panel source files live under `packages/backfield-agate/src/agate_nodes/*/ui`. The Agate UI
sync script copies them into the application and generates its node registry; edit the package
source, not the synchronized copies.

## Dependency direction

The dependency direction is from applications and orchestration packages toward domain and
infrastructure packages:

```text
UI applications -> HTTP APIs

agate-api -> backfield-auth, backfield-events, backfield-observability, agate-runtime, backfield-entities, backfield-db
core-api -> backfield-ai, backfield-auth, backfield-events, backfield-observability, agate-runtime, backfield-entities, backfield-db
stylebook-api -> backfield-ai, backfield-auth, backfield-observability, backfield-entities, backfield-db
worker -> backfield-ai, backfield-auth, backfield-events, backfield-observability, agate-runtime, backfield-entities, backfield-db

agate-runtime -> backfield-ai, backfield-entities, backfield-db
backfield-auth -> backfield-db
backfield-ai -> backfield-db
backfield-entities -> backfield-db
backfield-events -> backfield-db
backfield-cli -> backfield-db
backfield-observability -> (stdlib / typing only; no DB)
```

`backfield-db` does not depend on applications. Shared packages do not import API routers,
worker modules, or frontend application state. Application-specific orchestration stays in its
own app even when the underlying policy or storage helpers are shared.

The UI applications depend on `@backfield/ui`. Agate node panels use
`@backfield/ui/nodeOutputs` so browser result lookup follows the same stable output-key rules as
the Python executor.
