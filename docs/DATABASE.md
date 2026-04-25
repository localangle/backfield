# Database strategy (Backfield)

Backfield uses a **fresh schema**. Agate-owned tables use the **`agate_` prefix**. Cross-app **infrastructure** (orgs, users, projects, credentials) uses **`backfield_`**. The shared **content/location substrate** uses **`substrate_`** (articles, locations, mentions, occurrences, cache). Editorial Stylebook tables will use `stylebook_*`.

## Ownership


| Area                                             | Owner                   | Notes                                                                  |
| ------------------------------------------------ | ----------------------- | ---------------------------------------------------------------------- |
| Agate graphs, runs, templates                    | `packages/backfield-db` | Alembic migrations live here only                                      |
| Backfield orgs, users, projects, credentials     | `packages/backfield-db` | Same migration chain                                                   |
| Shared content/location substrate                | `packages/backfield-db` | `substrate_article`, `substrate_location`, mentions, occurrences, cache |
| Stylebook editorial / canonical tables           | `packages/backfield-db` | `stylebook`, `stylebook_location_canonical`, `stylebook_location_alias`; helpers in `packages/backfield-stylebook` |


Do **not** run multiple services that each invoke `alembic upgrade` on startup for the same revision path; pick **one** migration runner (the `agate-api` entrypoint on deploy, or `make migrate` locally).

## Current tables

### Identity and projects (`backfield_*`)

- `backfield_organization` — tenant; migration seeds a `default` org for single-org installs.
- `backfield_workspace` — optional sub-org grouping under an organization (generic naming; many projects per workspace). Each row references exactly one **`stylebook`** via **`stylebook_id`** (NOT NULL after revision **`011_stylebook_locations`**). Revision **`003_def_ws_general`** seeds a **`default`** workspace under the **`default`** org and sets the **General** project’s `workspace_id` to that row (so General lives under Organization → Workspace → Project).
- `backfield_user` — user identity (email, password hash, `disabled_at`).
- `backfield_organization_membership` — `(user_id, organization_id)` with `role` (`org_admin`, `member`, …).
- `backfield_project` — canonical project for Agate graphs, encrypted vault keys, Stylebook scoping, and future Core import APIs (`organization_id` required; `workspace_id` optional but new/bootstrap flows should set it).
- `backfield_workspace_membership` — `(user_id, workspace_id)` unique; grants a **member** access to every project whose `workspace_id` is that workspace (same org). Unioned in auth with legacy `backfield_project_membership` rows until the latter are fully deprecated.
- `backfield_project_membership` — `(user_id, project_id)` with optional per-project `role` (legacy explicit grants).
- `backfield_api_credential` — per-project API keys (`credential_type` `user` or `service`), `key_prefix` + `key_hash`, `revoked_at`.

### Shared content and locations (`substrate_*`)

- `substrate_article` — project-scoped content item for stateful ingestion. Uses a project-scoped external identity hierarchy with `(project_id, url)` as the fallback uniqueness rule. `source_run_id` stores the executing `agate_run.id` (UUID string) when the row is produced from an Agate worker run.
- `substrate_image` — images attached to a `substrate_article`.
- `substrate_location` — durable shared location entity row. Stores normalized naming, provider identity/fingerprint, **substrate** `status` (e.g. `resolved`, `needs_review`), PostGIS geometry, optional **`stylebook_location_canonical_id`** (nullable FK to `stylebook_location_canonical`), and **`canonical_link_status`** (`unlinked`, `pending`, `linked`, `waived` — minimal v1 set) plus optional **`canonical_review_reasons_json`** for deferral/adjudication metadata. **Invariant:** `linked` if and only if `stylebook_location_canonical_id` is set; other statuses require a null FK. **Stylebook candidate queue** (Stylebook API) lists rows with **`canonical_link_status = pending`** and null FK, not merely null FK. **`substrate_location_mention.needs_review`** remains for extraction/geocode uncertainty on the mention aggregate, not for canonical assignment. Indexes include **`ix_substrate_location_project_canonical`**, **`ix_substrate_location_project_link_status`** `(project_id, canonical_link_status)`, a Postgres **partial** index for the pending queue, and the legacy partial index on `(project_id)` where the canonical FK is null.
- `substrate_location_mention` — one aggregate article-to-location association per `(article_id, location_id)` with workflow state, provenance, `role_in_story`, primary **`nature`** (PlaceExtract editorial role: `primary`, `secondary`, `subject`, `context`, `person`, `unknown`), and optional **`nature_secondary_tags_json`** for extra roles.
- `substrate_location_mention_occurrence` — supporting evidence rows for a location mention aggregate (`mention_text`, offsets, labels, provenance). Editorial prose lives on the mention (`role_in_story`, `description` from extraction) — not duplicated here.
- `substrate_location_cache` — project-scoped dumb cache of external resolution results only. Cache rows are lookup accelerators, not the durable entity identity layer.

### Stylebook (`stylebook_*`)

- `stylebook` — org-scoped Stylebook catalog (`organization_id`, `slug`, `name`, `is_default`). Unique `(organization_id, slug)`. At most one **`is_default`** row per organization (partial unique index on Postgres). Migration **`011_stylebook_locations`** inserts a **Default Stylebook** (`slug` `default`) per existing org and sets **`backfield_workspace.stylebook_id`** for all workspaces in that org.
- `stylebook_location_canonical` — canonical location within a Stylebook; optional **`primary_substrate_location_id`** FK to `substrate_location` remains for legacy rows but is **deprecated for new linkage**—do not use it as the identity key for ingest or linking; prefer **`substrate_location.stylebook_location_canonical_id`** instead. Nullable **`location_type`** and **`formatted_address`** hold the authoritative catalog “place card” hints (bootstrapped once from the originating substrate on materialize / accept-create-new, or set via Stylebook API/UI); ingest updates those values on **substrate** rows only until a human edits the canonical. Optional **`geometry_json`**, **`geometry`**, and **`geometry_type`** mirror the substrate pattern so manual canonicals can participate in proximity-aware scoring when populated. **Linking policy:** ingest, recall, exact-alias, Stylebook suggestions, manual **`POST …/link-canonical`**, and LLM adjudication all use the same symmetric **`link_pair_allowed`** matrix in **`packages/backfield-stylebook/canonical_link_matrix.py`** (strict groups for country/state/county/city/neighborhood/**`region_city`**, explicit **address-like ↔ `place`** cross exception, both-fully-flexible otherwise). A canonical with **`location_type` null** is treated as flexible: a **strict** substrate (e.g. `city`) will **not** autolink to it—backfill types on legacy canonicals if they should accept strict-tier rows.
- `stylebook_location_alias` — alias strings keyed to a canonical row (`normalized_alias`, **`provenance`**, optional suppression). Unique `(location_canonical_id, normalized_alias)`. On Postgres, revision **`014_pg_trgm_canon_geom`** adds a **GIN `pg_trgm`** index on **`normalized_alias`** for fuzzy recall (requires **`CREATE EXTENSION IF NOT EXISTS pg_trgm`** in that migration).

### Agate execution (`agate_*`)

- `agate_graph` — stored graph spec (JSON), FK to `backfield_project`.
- `agate_run` — execution record, status, result/error JSON.
- `agate_processed_item` — per-S3-object work unit for **S3Input** batch runs: FK to `agate_run.id`, optional `source_file` (S3 key), optional `input_json` (full valid document), `status` (`pending` / `running` / `succeeded` / `failed` / `skipped`), optional `error_message` / `result_json`, timestamps. Indexed on `run_id`.
- `agate_template` — curated template flows (`spec_json`); instantiated as new `agate_graph` rows.

Schema revisions start at `001_agate_baseline` (initial `agate_*` tables and seed rows). Revision **`002_backfield_identity`** adds identity tables, renames `agate_project` → `backfield_project` (adds `organization_id`, optional `workspace_id`), and renames `agate_project_secret` → `backfield_project_secret`. Revision **`002_starter_flow_layout`** (runs next) is a **data migration** that rewrites stored `spec_json` for graphs named `Starter flow` (and the seeded **Geocode pipeline** template) so node positions match the UI card widths—run `make migrate` so existing databases pick up the layout fix.

### Secrets

- `backfield_project_secret` — per-project encrypted env-style secrets (`key` + `value_encrypted`); decrypted by the worker at run time when `MASTER_ENCRYPTION_KEY` is set.

Revision **`003_def_ws_general`** inserts the **Default Workspace** (`slug` `default`) and links General to it (org display name is seeded as **Backfield** in `002_backfield_identity`). Revision **`004_ws_membership`** adds `backfield_workspace_membership`. Revision **`005_location_schema_foundation`** introduces the shared content/location substrate under historical `backfield_*` table names (since renamed—see **`009_rename_substrate_tables`**) and enables PostGIS for location geometry. Revision **`006_article_source_run_id_text`** aligns article `source_run_id` with string `agate_run.id` values (and adds the ORM-level foreign key).

Revision **`007_starter_flow_add_db_output`** rewrites stored **Starter flow** `agate_graph.spec_json` rows to the canonical starter spec that includes **`DBOutput`** (so local stacks pick up persistence gating without manual graph edits).

Revision **`008_drop_occurrence_context_text`** drops **`context_text`** from the location mention occurrence table (redundant with extraction `description` / mention fields). Revision **`009_rename_substrate_tables`** renames substrate tables and related indexes/constraints from `backfield_*` to **`substrate_*`** so `backfield_*` stays reserved for tenancy and infrastructure.

Revision **`011_stylebook_locations`** adds **`stylebook`**, **`stylebook_location_canonical`**, **`stylebook_location_alias`**, and **`backfield_workspace.stylebook_id`** with per-org default Stylebook backfill.

Revision **`012_substrate_sb_canon_fk`** adds **`substrate_location.stylebook_location_canonical_id`** (nullable FK, `ON DELETE SET NULL`) and supporting indexes for workspace-scoped candidate queues and accepts.

Revision **`013_substrate_slc_status`** adds **`canonical_link_status`** (default `unlinked`) and **`canonical_review_reasons_json`**, backfills **`linked`** where a canonical FK was already set, and adds queue-oriented indexes.

Revision **`014_pg_trgm_canon_geom`** enables **`pg_trgm`** on Postgres (extension creation is not caught—migration fails if the extension cannot be installed), adds the trigram index on **`stylebook_location_alias.normalized_alias`**, and adds optional geometry columns on **`stylebook_location_canonical`**. Non-Postgres upgrades skip the extension and trigram index; **`geometry`** is stored as plain text where PostGIS is not used.

Revision **`015_canon_geo_meta`** adds nullable **`location_type`** and **`formatted_address`** text columns on **`stylebook_location_canonical`**.

Revision **`016_agate_processed_item`** creates **`agate_processed_item`** with FK to **`agate_run.id`** (`ON DELETE CASCADE`) and index **`ix_agate_processed_item_run_id`**.

The **Starter flow** graph row for the General project is created at runtime when `BACKFIELD_LOCAL_BOOTSTRAP=1` on `agate-api` startup (see [docs/OPERATIONS.md](OPERATIONS.md)), not by the baseline migration alone.

**Existing databases** that already applied older revisions: follow migration notes in your upgrade path or reset (`make reset-db` + `make up`) for dev.

## Indexing expectations

- Tables must stay namespaced by owning app prefix.
- Add indexes for expected lookup, join, and filter paths as part of the schema change.
- Intentional indexes include:
  - `backfield_project.slug`
  - `agate_run.graph_id`
  - `agate_processed_item.run_id`
  - `backfield_project_secret.project_id`
  - unique key on `backfield_project_secret (project_id, key)`
  - GIST indexes on shared location geometry columns
- If a new query path matters for runtime behavior, capture the indexing decision in the migration or model change rather than leaving it implicit.

## Redesign space

- Prefer additive migrations early; rename columns via explicit migrations once naming stabilizes.
- When adding another app’s tables, use that app’s prefix and document it here.
