# Processed-item review

Processed-item review is an Agate API contract layered over immutable worker output. It supports locations, people, organizations, article fields, article metadata, and custom records.

Routes are under `/runs/{run_id}/items/{item_id}` and require access to the run's project.

## Item detail

`GET /runs/{run_id}/items/{item_id}` returns:

- parsed input and immutable execution `output`;
- node outputs, logs, timings, status, error, and tracked AI cost;
- stored `overlay` and integer `overlay_version`;
- materialized `reviewed_output` when review content has been saved;
- merged location, person, and organization lanes plus stale overlay entries;
- article context;
- article metadata rows;
- semantic indexing, article embedding, and automatic connection summaries.

Synthetic `items/1` views are available for whole-flow runs without a stored processed-item row. Review mutations require a real processed item and return `404` for a synthetic view.

## Overlay writes and concurrency

`PATCH /runs/{run_id}/items/{item_id}` replaces the complete overlay. The request must include `If-Match` with the current `overlay_version`; quoted integer values are accepted.

- A successful write increments `overlay_version`.
- A stale version returns `409` with the current version.
- Invalid supported geometry returns `400`.
- The API never mutates `result_json` when applying review edits.
- Item rerun clears the overlay, reviewed output, and version before requeueing execution.

Clients must merge their local edits into the latest complete overlay before sending the replacement payload.

## Entity review domains

Locations, people, and organizations use the same overlay pattern:

- `by_anchor` contains shallow patches for model rows;
- `removed_anchors` hides model rows;
- `user_added` contains reviewer-created rows with stable `user_place:`, `user_person:`, or `user_organization:` identifiers.

GET responses expose `merged_locations`, `merged_people`, and `merged_organizations`. Each lane combines the selected consolidated model output with review changes and may enrich rows with saved-entity identifiers, canonical links, Stylebook context, and mention occurrences. Stale arrays report patches whose anchors no longer exist in the current model output.

Locations additionally support:

- occurrence edits keyed by persisted or client identifiers;
- GeoJSON geometry validation and saved-entity geometry updates;
- article-scoped removal;
- explicit adoption of saved geometry by a linked canonical.

For read-only review display, a fully linked canonical's Stylebook geometry takes precedence over
the run's saved geography. The original run geometry remains unchanged for audit, editing, and
explicit adoption into the Stylebook.

Saved entity create, update, occurrence, geometry, link, and delete operations are owned by Stylebook API. Agate review keeps its overlay in step with those persisted edits.

## Article fields and metadata

`overlay.article` is shallow-merged into consolidated article payloads in reviewed output.

Article metadata review uses `article_meta.by_id`, `article_meta.user_added`, `article_meta.removed_ids`, and `article_meta.removed_meta_types`.

Dedicated routes create, update, and delete article metadata below the processed-item path. They use the same `If-Match` concurrency contract:

- persisted article rows update `substrate_article_meta`;
- output-only rows remain overlay changes;
- duplicate metadata types return `409`;
- every successful mutation rematerializes reviewed output.

`article_context` resolves the item's article within the run project's tenant. It prefers a valid persisted article and otherwise provides best-effort inline headline and body content with a resolution reason.

## Custom records

`custom_records.<record_type>` supports:

- `by_key` field and mention patches;
- `removed_keys`;
- reviewer `user_added` records;
- a validated `definition` for a record type created during review.

Record identity is the record type plus stable key. Reviewed output updates every matching custom-record block. When the item resolves to a persisted article, a custom-record overlay write also replaces the article's persisted custom records with the reviewed state. Items without a persisted article save only the overlay and reviewed output.

## Reviewed output

When an overlay contains review content, Agate API materializes a complete reviewed document into `reviewed_output_json`.

- Location edits update the selected consolidated places block.
- People and organization edits update their Stylebook Output or consolidated blocks.
- Article field and metadata edits update consolidated article payloads.
- Custom-record edits update every applicable custom-record block.

`reviewed_output` is an export representation. Worker execution and Backfield Output continue to use immutable execution output. Review does not update geocode cache or canonical catalog rows.

## S3 Output synchronization

`POST /runs/{run_id}/items/{item_id}/s3-sync` queues an overwrite of the S3 object recorded by S3 Output.

- Reviewed consolidated content is uploaded when present; otherwise original output is used.
- The bucket and key are the values recorded during execution.
- Success or failure state is stamped into the stored S3 Output payload.
- The item must have succeeded and contain an S3 Output upload record.

## Read-only review status

Item detail also summarizes semantic indexing, article embedding, and automatic connection work produced by Backfield Output. These fields inform review but are not edited through the general overlay transport.
