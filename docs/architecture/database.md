# Database architecture

`packages/backfield-db` is the source of truth for SQLModel tables, schema conventions,
encryption helpers, sessions, and Alembic migrations. Applications and other packages may query
these models but do not define parallel table contracts.

## Schema ownership

Table names identify their owning domain:

- `backfield_*` — tenancy, identity, credentials, secrets, and shared AI infrastructure.
- `agate_*` — flow definitions and execution.
- `substrate_*` — project-scoped ingested content, extracted entities, evidence, and search data.
- `stylebook*` — organization-scoped catalogs, canonicals, editorial metadata, relationships,
  activity, import/export jobs, and cleanup workflows.

All schema changes use the single Alembic chain under `packages/backfield-db/alembic`.

## Current tables

### Identity, access, and AI

- Organizations, workspaces, projects, and users:
  `backfield_organization`, `backfield_workspace`, `backfield_project`, `backfield_user`.
- Access grants and API keys: `backfield_organization_membership`,
  `backfield_workspace_membership`, `backfield_project_membership`,
  `backfield_api_credential`.
- Public request safety: `backfield_public_idempotency_record` stores a seven-day
  project/operation/key reservation, canonical request hash, linked Agate run, and
  retryable enqueue state (`pending` / `publishing` / `published`) with a Celery
  task descriptor. It never stores request bodies or credentials.
- Encrypted credentials: `backfield_project_secret`,
  `backfield_organization_integration_secret`.
- Shared AI catalog and accounting: `backfield_ai_model_config`,
  `backfield_ai_project_model_override`, `backfield_ai_default_model_role`,
  `backfield_ai_call_record`.

### Agate execution

- `agate_graph` stores a project-owned graph spec and public-run gate.
- `agate_template` stores reusable graph specs.
- `agate_run` stores parent execution status, graph snapshot payload, result, and error state.
- `agate_processed_item` stores per-document input, immutable model result, review overlay,
  reviewed output, status, and article provenance.
- `agate_node_timing` stores per-node wall-clock measurements for processed items.

### Substrate content and entities

- Content: `substrate_article`, `substrate_image`, `substrate_article_meta`,
  `substrate_custom_record`.
- Generated vectors: `substrate_article_embedding`, `substrate_image_embedding`.
- Locations: `substrate_location`, `substrate_location_mention`,
  `substrate_location_mention_occurrence`, `substrate_location_cache`,
  `substrate_location_semantic_document`.
- People: `substrate_person`, `substrate_person_mention`,
  `substrate_person_mention_occurrence`, `substrate_person_semantic_document`.
- Organizations: `substrate_organization`, `substrate_organization_mention`,
  `substrate_organization_mention_occurrence`,
  `substrate_organization_semantic_document`.

Substrate entity rows are project-scoped. Their mention rows aggregate an entity's relationship
to an article; occurrence rows preserve individual evidence spans. Canonical linkage is nullable
and points from a substrate entity to a Stylebook canonical. `canonical_link_status` distinguishes
unlinked, pending, linked, and waived rows, while `canonical_review_reasons_json` records the
decision trace and suggestions.

Entity `source_details_json` describes the latest project-scoped ingest of the shared entity.
Item-local extraction identity belongs on the article-scoped mention:
`source_details_json.raw_entry_id` records the processed-item row anchor for that article. Review
enrichment prefers this article anchor, then a unique domain identity match; positional anchors on
shared entity rows are not trusted because sibling batch items may reuse the same list indexes.

### Stylebook

- Catalog and access: `stylebook`, `stylebook_membership`, `stylebook_slug_redirect`.
- Locations: `stylebook_location_canonical`, `stylebook_location_alias`,
  `stylebook_location_meta`.
- People: `stylebook_person_canonical`, `stylebook_person_alias`, `stylebook_person_meta`.
- Organizations: `stylebook_organization_canonical`, `stylebook_organization_alias`,
  `stylebook_organization_meta`.
- Relationships and history: `stylebook_connections`, `stylebook_activity`.
- Transfer and review workflows: `stylebook_bundle_job`, `stylebook_cleanup_dismissal`,
  `stylebook_cleanup_ai_review`, `stylebook_cleanup_ai_proposal`,
  `stylebook_cleanup_check_run`, `stylebook_cleanup_check_result`,
  `stylebook_candidate_ai_review`.

Canonical ids are UUID strings. Canonical slugs are unique within a Stylebook, and aliases are
unique by canonical plus normalized alias. A Stylebook belongs to one organization; projects use
an explicit same-organization Stylebook or the organization's default.

Deleting a Stylebook reassigns workspaces and graph Stylebook refs, resets linked substrate rows
to pending, removes non-cascading dependents (activity, bundle jobs, cleanup and candidate AI
review rows), and deletes canonical trees before the catalog row itself.

## Shared entity field contracts

New entity domains follow the executable field-name contracts in
`packages/backfield-db/src/backfield_db/entity_contracts.py`:

- A substrate entity carries project ownership, display and normalized names, status, its
  type-specific canonical foreign key, link status and review reasons, external identity,
  identity fingerprint, source provenance, and timestamps.
- A mention links one substrate entity to an article and carries role, nature, review state,
  editor-change flags, source provenance, and timestamps.
- An occurrence links to a mention and preserves the grounded text, quote, character offsets,
  ordering, labels, suppression state, source provenance, and timestamps.
- A canonical carries Stylebook ownership, label, stable slug, status, optional primary-substrate
  compatibility link, and timestamps.
- An alias carries its type-specific canonical foreign key, original and normalized text,
  provenance, suppression state, and timestamps.
- A metadata row carries a project association, its type-specific canonical foreign key, metadata
  type and JSON value, editor-change flags, and creation time.

Type-specific models may add fields, but should not omit the shared contract without an explicit
architecture decision and matching test changes.

## Indexing

Models and migrations index expected ownership, join, queue, and lookup paths. Important
specialized indexes include:

- GIN full-text search over article headline, text, and URL;
- GIN trigram indexes for canonical labels and aliases used by recall and cleanup;
- GiST indexes on location geometry, including geography-cast indexes used by radius queries;
- project plus H3 resolution/cell indexes for map aggregation;
- partial pending-candidate indexes on substrate entity tables;
- unique identity fingerprints within a project and canonical slugs within a Stylebook;
- unique public idempotency keys within project and operation, plus expiry, run,
  and enqueue-state indexes for retention cleanup, run linkage, and publish recovery;
- run, processed-item, node-type, activity-feed, cleanup-run, and AI-call aggregation indexes.

Postgres uses PostGIS, `pg_trgm`, pgvector, and H3. Migrations create required extensions and fail
when the database role cannot install them.

## Connections and pooling

Runtime services use `BACKFIELD_DATABASE_URL`; local Compose routes it through PgBouncer in
transaction pooling mode. Migration and database-administration commands prefer
`BACKFIELD_DATABASE_URL_DIRECT` so DDL bypasses PgBouncer.

`backfield_db.session.get_engine()` provides one process-wide engine. Postgres connections disable
psycopg server-side prepared statements for transaction-pool compatibility. Optional pool size
and overflow come from `BACKFIELD_SQLALCHEMY_POOL_SIZE` and
`BACKFIELD_SQLALCHEMY_MAX_OVERFLOW`. API statement and lock limits are applied with `SET LOCAL`
per transaction. Short nested worker writes can use `null_pool_session`; normal request and task
code uses the shared engine and releases sessions around long graph or model execution.

## Secrets

Project and organization integration secrets are encrypted before storage and decrypted only in
authorized runtime paths. `MASTER_ENCRYPTION_KEY` must be identical in every service that reads or
writes encrypted values.

Project secrets use unique `(project_id, key)` identities. Organization integration secrets use
unique `(organization_id, integration_key)` identities and hold shared provider credentials.
AI model rows reference those integration secrets rather than storing provider keys in model
configuration or call-accounting rows. AI call records retain routing, usage, cost, latency, and
safe error metadata; they do not store prompts or responses.
