# Runtime architecture

## Run creation and dispatch

Agate API and Core API use `agate_runtime.run_trigger.trigger_agate_run` to create runs.
The trigger validates the stored `GraphSpec`, applies an optional public ingress override, and
stores the effective graph spec in `agate_run.result_json.graph_spec_json`. Workers execute that
snapshot so later graph edits do not change queued work.

TextInput and JSONInput runs create one `agate_processed_item` and enqueue
`execute_processed_item`. S3Input runs enqueue `execute_s3_batch_setup`, which:

1. Lists JSON objects under the snapshotted bucket and prefix.
2. Stores valid documents as `agate_processed_item` rows and records invalid or capped objects as
   skipped rows.
3. Dispatches valid items as a Celery chord on the `agate` queue.
4. Uses `finalize_s3_parent_run` to aggregate child statuses onto the parent `agate_run`.

Run replay clones replayable processed-item inputs and executes them against the graph snapshot
carried by the replay run.

## Item execution

`execute_processed_item` claims an item, loads its parent run and project, resolves project and
organization credentials, and releases its setup session before graph execution. It replaces the
graph's ingress runner with a shim backed by the item's `input_json`; S3 shims also add batch and
source-file metadata.

The worker calls `agate_runtime.executor.execute_graph` with worker-owned runners such as
Backfield Output. Node results are persisted on `agate_processed_item.result_json`; review
overlays remain separate, and `reviewed_output_json` holds the materialized reviewed result when
present. Node wall-clock measurements are stored in `agate_node_timing`. The parent run is
finalized after each single-item completion and by the S3 chord callback for batch runs.

`BACKFIELD_RUN_ID` remains the parent run id during item execution, so all Backfield Output writes
from a batch retain common run provenance.

## Graph scheduling and outputs

The executor always honors graph dependencies and rejects cycles. By default it executes ready
nodes sequentially. With `BACKFIELD_PARALLEL_GRAPH_LEVELS=1`, predecessor-ready nodes run
concurrently:

- ordinary nodes wait for their direct upstream nodes;
- JSON Output and Gather wait for all relevant non-downstream nodes;
- Backfield Output waits for its directly wired inputs and consolidates all completed node
  outputs available at that point.

Public result keys are stable snake_case names derived from node type and topological order.
`Output` maps to `json_output`, Backfield Output maps to `stylebook_output`, and repeated node
types receive deterministic suffixes.

## Backfield Output

Backfield Output consolidates article content and supported domains, then persists them through
worker handlers. Current handlers cover locations, people, and organizations; article metadata,
custom records, images, and article embeddings use their own persistence paths. Node settings
control:

- Stylebook matching and optional explicit Stylebook id;
- rules or AI-assisted canonicalization;
- automatic application of canonical decisions;
- `add_only`, `smart_merge`, or `replace` reconciliation;
- semantic-document synchronization and embedding;
- high-confidence automatic Stylebook connections.

An explicit Stylebook id must belong to the project's organization. Without an override,
Backfield Output resolves the organization's default Stylebook. A missing organization catalog
causes catalog-backed canonicalization to be skipped without discarding substrate persistence.

## Geocode cache path

When a worker supplies project context and a GeocodeAgent node enables cache,
`agate-runtime` attaches database-backed cache operations to its execution context. A node-level
Stylebook id enables exact canonical-label and active-alias lookup, canonical adjudication, and
materialization. The project-scoped `substrate_location_cache` fingerprint lookup remains
available without a Stylebook id. Type, content, component, and jurisdiction sanity checks can
reject a cache candidate so external geocoding or configured AI adjudication can run.

GeocodeAgent does not fall back to the organization's default Stylebook for canonical cache
operations. Runs without worker project context skip the database cache. When no database bundle
is attached, a cache-enabled node can still use an injected `cache_resolve` callable or a
configured Stylebook HTTP URL and project slug.

## Active compatibility behavior

These compatibility paths remain part of current execution:

- Workers prefer `agate_run.result_json.graph_spec_json` but fall back to the graph's current
  `spec_json` when a run has no snapshot.
- `execute_agate_run` still executes runs without processed-item rows and stores the whole graph
  result on `agate_run.result_json`; Agate API presents those runs as synthetic `items/1` views.
- Node Stylebook references accept both `stylebook_id` and the older `stylebookId` spelling.
- Backfield Output treats `replace_article_geography_on_persist` as `replace` only when the node
  has no explicit reconciliation policy.
- The UI reads current snake_case output keys, older `__outputKeysByNodeId` maps, and direct node-id
  keys.
