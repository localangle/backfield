# Agate API

Agate API is the control plane for projects, flows, templates, runs, processed items, and node metadata. It runs from `apps/agate-api`; workers execute queued flows.

Processed-item editing contracts are documented in [`processed-item-review.md`](processed-item-review.md).

## Authentication and tenancy

Authenticated routes accept:

- the signed browser `session` cookie;
- `Authorization: Bearer <SERVICE_API_TOKEN>`;
- a project-bound `bfk_…` API key.

Project, flow, and run access is checked against the resource's project. Organization admins see every project in their organization. Members see projects from workspace membership plus any explicit project grants that remain in use. A project API key can access only its bound project; the service token has automation-wide access.

`GET /health` and `GET /nodes/metadata` are intentionally unauthenticated.

## Route families

### Projects

`/projects` owns project creation, listing, detail, updates, deletion, statistics, tracked AI cost, and encrypted project secrets.

- List responses are filtered to visible projects.
- Project creation and workspace assignment validate organization and workspace access.
- Secret responses contain metadata, never secret values.
- Project responses expose the assigned workspace and effective workspace Stylebook context when available.

### Flows and templates

`/graphs` creates, lists, validates, updates, and deletes saved `GraphSpec` flows. Referenced node Stylebook identifiers must exist in the flow project's organization. Graph responses include descriptive and public-run settings used by Agate UI and Core API.

`/templates` lists flow templates and instantiates a template into a project after project-access checks.

Deleting a flow removes its run-control records and detaches durable article rows from deleted run identifiers; it does not treat durable article content as graph-owned data.

### Runs

`/runs` creates, replays, lists, inspects, cancels, and reports cost for runs.

- A run pins the effective graph specification before work is queued.
- S3 Input starts batch setup and creates one processed item per input object.
- Inline Text Input or JSON Input creates a processed item at trigger time.
- Run cancellation is available while pending or running. Cancellation atomically fails active
  items, preserves completed items, and returns the same compact status shape used for polling.
  Repeating cancellation returns that terminal status without changing the run again.
- Replay creates a new run from an existing run contract; item rerun requeues an existing processed item and clears its review state.

For active runs, poll `GET /runs/{run_id}/status` and page summaries through `GET /runs/{run_id}/items`. Full `GET /runs/{run_id}` remains supported for callers that need the complete run response.

`GET /runs/{run_id}/estimated-ai-cost` returns run totals and node-level attribution. Project statistics and project cost routes aggregate the same tracked call records at project scope.

### Processed items

Important item routes are:

- `GET /runs/{run_id}/items/{item_id}` for input, immutable execution output, review state, enriched review lanes, article context, indexing state, connection state, and item cost;
- `PATCH /runs/{run_id}/items/{item_id}` to replace the review overlay with optimistic concurrency;
- article metadata create, update, and delete routes below the item;
- `POST …/rerun` to requeue the item and clear overlay and reviewed output;
- `POST …/s3-sync` to overwrite the item's recorded S3 Output object with reviewed output when present.

Synthetic `items/1` views support whole-flow runs that have no stored processed-item row. They are readable, but mutations that require an `agate_processed_item` row reject them.

### Node metadata

`GET /nodes/metadata` returns node metadata shipped by the Agate package for dynamic UI use. Runtime node implementation remains in `packages/backfield-agate`; the API does not duplicate node definitions.

## Run lifecycle

1. Agate API validates project and flow access and stores a pending run with its pinned graph.
2. It queues batch setup or a processed-item task on the `agate` queue.
3. Workers move the run and items through running and terminal states and store execution output.
4. Clients use compact status and paged item routes while work is active.
5. Review changes remain separate from immutable execution output and may be exported or synchronized explicitly.

Core API's `/public/v1/projects/{project_slug}/runs` trigger uses the same run-trigger service. It additionally requires a project service key with `runs:trigger` and a flow whose public-run setting is enabled.

## Backfield Output persistence

Backfield Output persists consolidated article content and the domains present in its input. Current persisted content includes:

- locations, people, and organizations with article mentions and Stylebook matching;
- article identity, text, and images;
- article and image embeddings;
- article metadata;
- custom records;
- semantic mention documents when enabled;
- automatic entity connections when configured.

Entity reconciliation supports `add_only`, `smart_merge`, and `replace`. The policy applies to each current entity domain represented in the consolidated payload, and the node returns per-domain reconciliation summaries. Catalog matching resolves an explicit node Stylebook when configured, otherwise the organization's default Stylebook (or its first Stylebook by id).

Backfield Output persistence runs in the worker. The package-level runner is a no-op outside that worker context so local graph execution can still return the node's output shape.
