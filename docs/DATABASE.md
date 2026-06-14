# Database strategy (Backfield)

Backfield uses a **fresh schema**. Agate-owned tables use the **`agate_` prefix**. Cross-app **infrastructure** (orgs, users, projects, credentials) uses **`backfield_`**. The shared **content/location substrate** uses **`substrate_`** (articles, locations, mentions, occurrences, cache). Editorial Stylebook tables will use `stylebook_*`.

## Ownership


| Area                                             | Owner                   | Notes                                                                  |
| ------------------------------------------------ | ----------------------- | ---------------------------------------------------------------------- |
| Agate graphs, runs, templates                    | `packages/backfield-db` | Alembic migrations live here only                                      |
| Backfield orgs, users, projects, credentials     | `packages/backfield-db` | Same migration chain                                                   |
| Shared content/location substrate                | `packages/backfield-db` | `substrate_article`, `substrate_location`, mentions, occurrences, cache; worker ingest layout in [`ENTITY_TYPES.md`](ENTITY_TYPES.md) |
| Stylebook editorial / canonical tables           | `packages/backfield-db` | `stylebook`, `stylebook_location_canonical`, `stylebook_location_alias`, **`stylebook_location_meta`**, **`stylebook_connections`**; helpers in `packages/backfield-entities` |
| Shared AI model configuration and usage tracking | `packages/backfield-db` | `backfield_ai_*` tables for model catalog, project overrides, default roles, and LLM call cost records |


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

### Shared AI model infrastructure (`backfield_ai_*`)

- `backfield_ai_model_config` — organization-owned AI model configuration shared by Agate, Stylebook, and future Backfield AI features. Preset rows resolve routing from `provider` + `provider_model_id` and use org **built-in** provider keys (`ai.provider.*` secrets). Custom rows set optional **`litellm_model`** (full routing string) and optional **`integration_secret_id`** (FK to **`backfield_organization_integration_secret.id`** — expected **`integration_key`** prefix **`ai.credential.`**); `provider` / `provider_model_id` are still populated as a derived split for indexing and display. Multiple catalog rows may share the same **`integration_secret_id`** when set (non-unique index **`ix_bf_ai_model_integration_secret`**). Model kind (`generative` initially, with room for `embedding` later), text/JSON/vision capabilities, optional Decimal/Numeric token prices, currency (`USD` by default), status, and latest settings test metadata.
- `backfield_ai_project_model_override` — project-level availability override for an inherited organization model config. Unique `(project_id, model_config_id)` keeps one effective override per project/model. Optional **`integration_secret_id`** points at an org **`backfield_organization_integration_secret`** row keyed **`ai.project_model.{project_id}.{model_config_id}`** when this project stores its own provider credential for that catalog model (revision **`031_ai_prj_ovrd_secret`**).
- `backfield_ai_default_model_role` — default model role assignment scoped to exactly one organization or one project. Partial unique indexes enforce one assignment per `(organization_id, role)` or `(project_id, role)`.
- `backfield_ai_call_record` — one execution attempt to call an AI model. Records project, optional Agate run/processed-item/node context, resolved provider/model snapshot metadata, `model_kind` (`generative` or `embedding`), token usage, estimated Decimal/Numeric cost, ``cost_estimate_source`` (for example `litellm` when the dollar amount comes from LiteLLM’s calculator, `manual` if Backfield derives cost from token counts × configured rates, `unavailable` when no response was priced), currency, incomplete-estimate flag, latency, request id, and safe error metadata. Prompt and response content are intentionally not stored. On the Celery worker, `run_id`, React Flow `node_id` / node type, batch `processed_item_id` (when applicable), and pinned `model_config_id` are populated for traced LiteLLM **completions** (`agate_utils.llm.call_llm`) and **embedding** batches (`backfield_ai.embeddings.embed_texts_for_model_config` during semantic indexing on Backfield Output, including batch `processed_item_id` when the graph runs per-file).

### Shared entity fields

New entity types (person, organization, work, …) follow the same **substrate trio** and **Stylebook canonical trio** as location. Per-entity FK column names differ (`stylebook_person_canonical_id`, `person_id`, …); shared shapes are documented in `packages/backfield-db/src/backfield_db/entity_contracts.py` and tested against location and person models.

**Substrate entity** (`substrate_<type>`): `project_id`, `name`, `normalized_name`, `status`, nullable Stylebook canonical FK, `canonical_link_status`, `canonical_review_reasons_json`, optional `external_source` / `external_id`, `identity_fingerprint`, `source_kind`, `source_details_json`, `created_at`, `updated_at`, plus type-specific columns (location adds PostGIS geometry, geocode fields, …; person adds `title`, `affiliation`, `public_figure`, `person_type`; organization adds **`organization_type`** only).

**Substrate mention** (`substrate_<type>_mention`): one row per `(article_id, <type>_id)` with editorial flags (`needs_review`, `added`, `edited`, `deleted`), provenance JSON, optional `role_in_story` / `nature`, `created_at`, `updated_at`.

**Substrate mention occurrence** (`substrate_<type>_mention_occurrence`): evidence spans (`mention_text`, `quote_text`, offsets, `labels_json`, `suppressed`, …).

**Stylebook canonical** (`stylebook_<type>_canonical`): **`id` is a UUID string** for all **new** types (same as location after revision **`019_stylebook_loc_canon_uuid`**). Shared columns: `stylebook_id`, `label`, `slug` (unique per Stylebook), `status`, timestamps, plus type-specific catalog fields.

**Stylebook alias** and **meta**: alias rows (`alias_text`, `normalized_alias`, `provenance`, `suppressed`); meta rows (`meta_type`, `data_json`, soft `added` / `edited` / `deleted`).

**Consolidated JSON keys** (Agate `DBOutput` merge): derived from entity slug in `backfield_entities.registry.entity_types` — e.g. `person` → `people`, `location` → `places` (legacy). Types without Agate review tabs use the same key rule.

**Identity fingerprint:** `backfield_entities.registry.entity_types.compute_identity_fingerprint` hashes normalized name plus type-specific inputs for dedupe across ingests (location may keep geocode-specific fingerprint paths until unified).

### Shared content and locations (`substrate_*`)

- `substrate_article` — project-scoped content item for stateful ingestion. Uses a project-scoped external identity hierarchy with `(project_id, url)` as the fallback uniqueness rule. `source_run_id` stores the executing `agate_run.id` (UUID string) when the row is produced from an Agate worker run. Public article keyword search uses PostgreSQL full-text search over `headline`, `text`, and `url` (GIN index **`idx_substrate_article_fulltext`**, revision **`047_substrate_article_fulltext`**); semantic article search remains a separate future surface over **`substrate_article_embedding`**.
- `substrate_image` — images attached to a `substrate_article`.
- `substrate_image_embedding` — one pgvector row per `substrate_image` (Embed Images node → DBOutput persist): `generated_text`, optional vision model metadata, `embedding_model`, `embedding_dimensions`, optional `embedding_ai_model_config_id`, `embedding`, timestamps. Unique on `substrate_image_id` FK to `substrate_image`.
- `substrate_article_embedding` — one pgvector row per article (Embed Text node → DBOutput persist): `embedded_text`, `embedding_model`, `embedding_dimensions`, optional `embedding_ai_model_config_id`, `embedding`, timestamps. Unique on `article_id` FK to `substrate_article`.
- `substrate_article_meta` — article metadata tags (Article Metadata node → DBOutput persist): `category`, `rationale`, `confidence` (0–1), optional `prompt_preset`, optional `source_run_id` FK to `agate_run`, timestamps. Unique on `(article_id, meta_type, category)` so multi-value presets such as **Subject** can persist up to three rows per article.
- `substrate_custom_record` — user-defined extracted records (Custom Extract node → DBOutput persist): `record_type` (node-declared slug), `record_index` (row order), `fields_json` (flat field values), `mentions_json` (evidence mentions), `field_schema_json` (snapshot of the declared field schema so historical rows render after node edits), optional `confidence`, optional `source_run_id` FK to `agate_run`, timestamps. Unique on `(article_id, record_type, record_index)`; persistence replaces all rows per `(article_id, record_type)` on re-ingest. JSON field values are not individually indexed in v1.
- `substrate_location` — durable shared location entity row. Stores normalized naming, provider identity/fingerprint, **substrate** `status` (e.g. `resolved`, `needs_review`), PostGIS geometry, optional native H3 metadata (**`h3_cell`**, **`h3_resolution`** — derived spatial index for map aggregation; not place identity), optional **`stylebook_location_canonical_id`** (nullable FK to **`stylebook_location_canonical.id`** as a **UUID string**), and **`canonical_link_status`** (`unlinked`, `pending`, `linked`, `waived` — minimal v1 set) plus optional **`canonical_review_reasons_json`** for deferral/adjudication metadata. Worker ingest sets **`external_source`** / **`external_id`** from geocode results; Stylebook canonical hits use **`stylebook_location`** + **`stylebook:{canonical_uuid}`** for coarse types (city, state, county, region, town). Fine-grained POIs (`place`, `point`, `address`, intersections, `street_road`) that share one canonical still get **distinct** substrate rows via **`stylebook:{canonical_uuid}:{normalized_display_name_slug}`** so unlike names (e.g. Carson's vs Kohl's) do not overwrite each other's geometry or mentions. Upstream geocoder ids prefixed with **`h3:`** remain non-identifying buckets (distinct POIs in the same cell stay separate rows). Nullable **`geocode_router_audit_json`** stores the GeocodeAgent **route_strategy** audit when ingest payloads include **`agate_geocode_router_audit`** (latest ingest wins on merge). **Invariant:** `linked` if and only if `stylebook_location_canonical_id` is set; other statuses require a null FK. **Stylebook candidate queue** (Stylebook API) lists rows with **`canonical_link_status = pending`** and null FK, not merely null FK. **`substrate_location_mention.needs_review`** remains for extraction/geocode uncertainty on the mention aggregate, not for canonical assignment. Indexes include **`ix_substrate_location_project_canonical`**, **`ix_substrate_location_project_link_status`** `(project_id, canonical_link_status)`, **`idx_substrate_location_project_h3_resolution`**, **`idx_substrate_location_project_h3_cell`**, a Postgres **partial** index for the pending queue, and the legacy partial index on `(project_id)` where the canonical FK is null.
- `substrate_location_mention` — one aggregate article-to-location association per `(article_id, location_id)` with workflow state, provenance, `role_in_story`, primary **`nature`** (PlaceExtract editorial role: `primary`, `secondary`, `subject`, `context`, `person`, `unknown`), and optional **`nature_secondary_tags_json`** for extra roles.
- `substrate_location_mention_occurrence` — supporting evidence rows for a location mention aggregate (`mention_text`, optional `quote_text`, offsets, labels, provenance). **Multiple active rows per mention** are expected when PlaceExtract emits several `mentions[]` for the same place (or when Agate Review saves edits). **`source_kind`**: `system_extraction` (worker ingest; replaced on re-ingest except user rows), `user_review` (Agate Review **`PUT …/mention-occurrences`**), `manual_add` (Agate Review add-place flow; stores selected source passage as `quote_text` and exact place words as `mention_text`), `user_edit` (preserved across re-ingest). Re-ingest suppresses prior `system_extraction` rows for that mention, then inserts a fresh set. Editorial prose lives on the mention (`role_in_story`, `description` from extraction) — not duplicated on occurrences.
- `substrate_location_cache` — project-scoped dumb cache of external resolution results only. Cache rows are lookup accelerators, not the durable entity identity layer. Mirrors substrate **`h3_cell`** / **`h3_resolution`** when geometry is cached.
- `substrate_person` — durable shared person entity row. Shared substrate columns plus **`title`**, **`affiliation`**, **`public_figure`**, **`person_type`** (extract JSON field `type`), and optional **`sort_key`** (lowercase last name for list ordering). Optional **`stylebook_person_canonical_id`** (UUID FK), **`canonical_link_status`**, **`identity_fingerprint`** (normalized name + title + affiliation). Indexes mirror location: project + canonical, project + link status, project + type, project + public figure, project + sort key, pending-queue partial index on Postgres.
- `substrate_person_mention` — one aggregate article-to-person association per `(article_id, person_id)` with **`role_in_story`**, **`nature`** (person editorial role: `subject`, `source`, `expert`, `official`, `witness`, `affected`, `victim`, `suspect`, `participant`, `observer`, `context`, `other`), optional **`nature_secondary_tags_json`**, and review/provenance fields.
- `substrate_person_mention_occurrence` — evidence spans for a person mention aggregate (`mention_text`, optional `quote_text`, offsets, labels, provenance).
- `substrate_person_semantic_document` — occurrence-level semantic index row for person evidence (`search_text`, `source_hash`, `active` / `stale`, embedding status and metadata, pgvector **`embedding`**). Unique per **`person_mention_occurrence_id`**. Stylebook canonical is resolved at query time via **`person_id`** → **`substrate_person.stylebook_person_canonical_id`**.
- `substrate_organization` — durable shared organization entity row. Shared substrate columns plus **`organization_type`** (extract JSON field `type`). Optional **`stylebook_organization_canonical_id`** (UUID FK), **`canonical_link_status`**, **`identity_fingerprint`** (normalized name + organization_type). Indexes mirror person: project + canonical, project + link status, project + type, pending-queue partial index on Postgres.
- `substrate_organization_mention` — one aggregate article-to-organization association per `(article_id, organization_id)` with **`role_in_story`**, **`nature`** (`primary`, `actor`, `source`, `subject`, `affected`, `regulator`, `context`, `other`), optional **`nature_secondary_tags_json`**, and review/provenance fields.
- `substrate_organization_mention_occurrence` — evidence spans for an organization mention aggregate (`mention_text`; organizations do not use **`quote_text`** from extract).
- `substrate_organization_semantic_document` — occurrence-level semantic index row for organization evidence (same column pattern as person/location). Unique per **`organization_mention_occurrence_id`**. Work semantic tables follow the same pattern when that type has occurrence tables.
- `substrate_location_semantic_document` — same shape for location occurrences (unique **`location_mention_occurrence_id`**; canonical via **`location_id`** → **`substrate_location.stylebook_location_canonical_id`**).

### Stylebook (`stylebook_*`)

- `stylebook` — org-scoped Stylebook catalog (`organization_id`, `slug`, `name`, `is_default`). Unique `(organization_id, slug)` and unique `(organization_id, name)` (revision **`023_sb_name_unique_redirect`**). At most one **`is_default`** row per organization (partial unique index on Postgres; SQLite uses `sqlite_where`). Migration **`011_stylebook_locations`** inserts a **Default Stylebook** (`slug` `default`) per existing org and sets **`backfield_workspace.stylebook_id`** for all workspaces in that org.
- `stylebook_slug_redirect` — prior catalog slug for a `stylebook` row after rename; unique `(organization_id, old_slug)`; supports resolving old URL segments to the current row (revision **`023_sb_name_unique_redirect`**; FKs `ON DELETE CASCADE` to org and stylebook).
- `stylebook_location_canonical` — canonical location within a Stylebook. **`id`** is a **UUID string** primary key (same pattern as **`agate_run.id`**). **`slug`** is required, **immutable** after insert, and **unique per `stylebook_id`** (allocated from the initial label with numeric suffixes on collision). Optional **`primary_substrate_location_id`** FK to `substrate_location` remains for legacy rows but is **deprecated for new linkage**—do not use it as the identity key for ingest or linking; prefer **`substrate_location.stylebook_location_canonical_id`** instead. Nullable **`location_type`** and **`formatted_address`** hold the authoritative catalog “place card” hints (bootstrapped once from the originating substrate on materialize / accept-create-new, or set via Stylebook API/UI); ingest updates those values on **substrate** rows only until a human edits the canonical. Optional **`geometry_json`**, **`geometry`**, and **`geometry_type`** mirror the substrate pattern so manual canonicals can participate in proximity-aware scoring when populated. Optional **`h3_cell`** and **`h3_resolution`** mirror substrate native H3 metadata when geometry is present. Nullable **`country_code`**, **`subdivision_code`**, and **`city_name`** (revision **`021_sb_canon_jurisdiction`**) hold structured jurisdiction parsed from PlaceExtract **`components`** on materialize / accept-create-new, with a best-effort backfill on existing rows from trailing label segments. Nullable **`district_kind`**, **`district_number`**, and **`district_key`** (revision **`022_sb_canon_district`**, index on **`district_key`**) copy PlaceExtract **`components.district`** identity when materializing or accepting **create-new** so **`political_district`** autolink and adjudication can compare stable keys. **Autolink policy:** `canonical_policy.decide_canonical_persist_plan` applies **`link_pair_allowed`** (type deny-list), **`autolink_container_to_fine_denied`**, recall scoring jurisdiction checks against these columns, and substrate preflight gates (see [docs/ARCHITECTURE.md](ARCHITECTURE.md)). Manual **`POST …/link-canonical`** may still set **`enforce_type_gate`** to apply **`link_pair_allowed`** only.
- `stylebook_location_alias` — alias strings keyed to a canonical row (`location_canonical_id` stores the canonical UUID string; **`normalized_alias`**, **`provenance`**, optional suppression). Unique `(location_canonical_id, normalized_alias)`. On Postgres, revision **`014_pg_trgm_canon_geom`** adds a **GIN `pg_trgm`** index on **`normalized_alias`** for fuzzy recall (requires **`CREATE EXTENSION IF NOT EXISTS pg_trgm`** in that migration).
- `stylebook_person_canonical` — canonical person within a Stylebook. **`id`** is a **UUID string** primary key; **`slug`** is required and unique per **`stylebook_id`**. Mirrors substrate editorial fields: **`title`**, **`affiliation`**, **`public_figure`**, **`person_type`**, and optional **`sort_key`**. Optional deprecated **`primary_substrate_person_id`** FK; prefer **`substrate_person.stylebook_person_canonical_id`** for linkage.
- `stylebook_organization_canonical` — canonical organization within a Stylebook. **`id`** is a **UUID string** primary key; **`slug`** is required and unique per **`stylebook_id`**. Type-specific field: **`organization_type`**. Optional deprecated **`primary_substrate_organization_id`** FK; prefer **`substrate_organization.stylebook_organization_canonical_id`** for linkage.
- `stylebook_person_alias` — alias strings for a person canonical (`person_canonical_id` UUID FK). Unique `(person_canonical_id, normalized_alias)`. Postgres **GIN `pg_trgm`** index on **`normalized_alias`** (revision **`036_person_schema`**, requires **`pg_trgm`** from **`014`**).
- `stylebook_person_meta` — JSON metadata rows per canonical person and project (`meta_type`, `data_json`, soft delete flags).

### Agate execution (`agate_*`)

- `agate_graph` — stored graph spec (JSON), optional human-readable **`description`** (plain text, default empty), FK to `backfield_project`.
- `agate_run` — execution record, status, result/error JSON. Boolean **`replace_article_geography_on_persist`** remains for legacy queued-run compatibility, but saved geography behavior now comes from the Backfield Output `reconciliation_policy` stored in graph node params.
- `agate_processed_item` — per-S3-object work unit for **S3Input** batch runs: FK to `agate_run.id`, optional `source_file` (S3 key), optional `input_json` (full valid document), `status` (`pending` / `running` / `succeeded` / `failed` / `skipped`), optional `error_message` / `result_json` (immutable model output), optional **`overlay_json`** (human review overlay) and integer **`overlay_version`** (optimistic concurrency for overlay PATCH; default `0`), optional **`reviewed_output_json`** (materialized `result_json` + overlay for export/display; cleared with overlay on rerun), legacy boolean **`replace_article_geography_on_persist`** (default `false`), timestamps. Indexed on `run_id`.
- `agate_template` — curated template flows (`spec_json`); instantiated as new `agate_graph` rows.

Schema revisions start at `001_agate_baseline` (initial `agate_*` tables and seed rows). Revision **`002_backfield_identity`** adds identity tables, renames `agate_project` → `backfield_project` (adds `organization_id`, optional `workspace_id`), and renames `agate_project_secret` → `backfield_project_secret`. Revision **`002_starter_flow_layout`** (runs next) is a **data migration** that rewrites stored `spec_json` for graphs named `Starter flow` (and the seeded **Geocode pipeline** template) so node positions match the UI card widths—run `make migrate` so existing databases pick up the layout fix.

### Secrets

- `backfield_project_secret` — per-project encrypted env-style secrets (`key` + `value_encrypted`); decrypted by the worker at run time when `MASTER_ENCRYPTION_KEY` is set.
- `backfield_organization_integration_secret` — per-organization encrypted integration secrets (`integration_key` + `value_encrypted`), optional nullable **`credential_display_name`** (UI-facing label), optional **`api_base`** for vendors that need a fixed endpoint URL (Azure-compatible hosts, etc.), unique `(organization_id, integration_key)`. AI flows use stable **`ai.provider.*`** slots plus arbitrary **`ai.credential.<uuid>`** rows for extra vendors (Core API org-admin routes); intended for broader integrations later.

Revision **`003_def_ws_general`** inserts the **Default Workspace** (`slug` `default`) and links General to it (org display name is seeded as **Backfield** in `002_backfield_identity`). Revision **`004_ws_membership`** adds `backfield_workspace_membership`. Revision **`005_location_schema_foundation`** introduces the shared content/location substrate under historical `backfield_*` table names (since renamed—see **`009_rename_substrate_tables`**) and enables PostGIS for location geometry. Revision **`006_article_source_run_id_text`** aligns article `source_run_id` with string `agate_run.id` values (and adds the ORM-level foreign key).

Revision **`007_starter_flow_add_db_output`** rewrites stored **Starter flow** `agate_graph.spec_json` rows to the canonical starter spec that includes **`DBOutput`** (so local stacks pick up persistence gating without manual graph edits).

Revision **`008_drop_occurrence_context_text`** drops **`context_text`** from the location mention occurrence table (redundant with extraction `description` / mention fields). Revision **`009_rename_substrate_tables`** renames substrate tables and related indexes/constraints from `backfield_*` to **`substrate_*`** so `backfield_*` stays reserved for tenancy and infrastructure.

Revision **`011_stylebook_locations`** adds **`stylebook`**, **`stylebook_location_canonical`**, **`stylebook_location_alias`**, and **`backfield_workspace.stylebook_id`** with per-org default Stylebook backfill.

Revision **`012_substrate_sb_canon_fk`** adds **`substrate_location.stylebook_location_canonical_id`** (nullable FK, `ON DELETE SET NULL`) and supporting indexes for workspace-scoped candidate queues and accepts.

Revision **`013_substrate_slc_status`** adds **`canonical_link_status`** (default `unlinked`) and **`canonical_review_reasons_json`**, backfills **`linked`** where a canonical FK was already set, and adds queue-oriented indexes.

Revision **`014_pg_trgm_canon_geom`** enables **`pg_trgm`** on Postgres (extension creation is not caught—migration fails if the extension cannot be installed), adds the trigram index on **`stylebook_location_alias.normalized_alias`**, and adds optional geometry columns on **`stylebook_location_canonical`**. Non-Postgres upgrades skip the extension and trigram index; **`geometry`** is stored as plain text where PostGIS is not used.

Revision **`015_canon_geo_meta`** adds nullable **`location_type`** and **`formatted_address`** text columns on **`stylebook_location_canonical`**.
Revision **`017_sb_loc_meta_conn`** adds **`stylebook_location_meta`** (JSON metadata per catalog canonical + project) and **`stylebook_connections`** (directed edges between canonical entities within a project, polymorphic int ids + **`nature`**). Revision **`018_drop_sb_loc_meta_key`** removes legacy **`meta_key`** from **`stylebook_location_meta`** on databases that created the column from an older revision of `017`.

Revision **`019_stylebook_loc_canon_uuid`** is a **destructive** upgrade: it replaces integer **`stylebook_location_canonical.id`** with **UUID strings**, adds **`slug`**, retargets **`stylebook_location_alias`**, **`stylebook_location_meta`**, and **`substrate_location.stylebook_location_canonical_id`** to the new key type, and migrates **`stylebook_connections.from_entity_id` / `to_entity_id`** to **TEXT** (UUID strings for **`location`** endpoints; decimal strings for stub person/org/work ids). It does **not** preserve existing canonical rows—local and dev databases should **`make reset-db`** (or otherwise wipe the Postgres volume) once before running **`make migrate`** after pulling this revision.

Revision **`020_sub_geocode_router_audit`** adds nullable **`substrate_location.geocode_router_audit_json`** (JSON/JSONB on Postgres) for optional GeocodeAgent **route_strategy** router audit payloads persisted by the worker.

Revision **`021_sb_canon_jurisdiction`** adds nullable **`country_code`**, **`subdivision_code`**, and **`city_name`** on **`stylebook_location_canonical`** (plus supporting indexes) and best-effort backfill of country/subdivision from trailing **`label`** segments.

Revision **`022_sb_canon_district`** adds nullable **`district_kind`**, **`district_number`**, and **`district_key`** on **`stylebook_location_canonical`** plus index **`ix_stylebook_location_canonical_district_key`**.

Revision **`023_sb_name_unique_redirect`** adds unique **`(organization_id, name)`** on **`stylebook`** and creates **`stylebook_slug_redirect`** for rename redirect history.

Revision **`016_agate_processed_item`** creates **`agate_processed_item`** with FK to **`agate_run.id`** (`ON DELETE CASCADE`) and index **`ix_agate_processed_item_run_id`**.

Revision **`033_agate_processed_item_overlay`** adds nullable **`overlay_json`** and non-null **`overlay_version`** (default `0`) for run-scoped review overlay storage and optimistic concurrency.

Revision **`034_replace_article_geography`** adds **`replace_article_geography_on_persist`** (boolean, default `false`) on **`agate_run`** and **`agate_processed_item`** for one-shot full geography replace on the next worker persist after a confirmed re-run or Run Again.

Current behavior: new runs and reruns no longer set that flag for normal UI paths. Backfield Output uses its node-level `reconciliation_policy` (`add_only`, `smart_merge`, or `replace`) to reconcile saved Places and returns summary counts in node output. The legacy flag is still honored as Replace when no node policy is present, so older queued work has a deterministic path.

Revision **`035_reviewed_output_json`** adds nullable **`reviewed_output_json`** for eager materialization of reviewed run output (see `docs/API.md` → *Reviewed output*).

Revision **`036_person_schema`** adds the person **substrate trio** (`substrate_person`, mentions, occurrences) and **Stylebook trio** (`stylebook_person_canonical`, alias, meta) with UUID canonical ids, slug uniqueness per Stylebook, fingerprint uniqueness per project, and queue-oriented indexes aligned with location.

Revision **`037_person_sort_key`** adds optional **`sort_key`** (lowercase last name) on **`substrate_person`** and **`stylebook_person_canonical`**, plus `(project_id, sort_key)` / `(stylebook_id, sort_key)` indexes for list ordering.

Revision **`038_substrate_semantic_docs`** enables **`vector`** on Postgres (requires the pgvector extension in the server image—same operational posture as **`pg_trgm`** in **`014`**), and adds **`substrate_person_semantic_document`** and **`substrate_location_semantic_document`**: one row per mention occurrence, **`search_text`** / **`source_hash`**, **`active`** / **`stale`**, embedding status and metadata, and nullable pgvector **`embedding`**. Canonical linkage is not denormalized—join **`person_id`** / **`location_id`** to substrate entity rows at query time. Non-Postgres migration paths store **`embedding`** as plain text.

Revision **`039_organization_schema`** adds the organization **substrate trio**, **Stylebook trio** (`stylebook_organization_canonical`, alias, meta), and **`substrate_organization_semantic_document`**, with UUID canonical ids, slug uniqueness per Stylebook, fingerprint uniqueness per project (`normalized_name` + **`organization_type`**), and queue-oriented indexes aligned with person.

Revision **`040_sb_conn_evidence`** adds nullable **`evidence_json`** on **`stylebook_connections`** (creation evidence for auto-linked edges) and unique **`uq_stylebook_connection_exact_edge`** on **`(project_id, from_entity_type, from_entity_id, to_entity_type, to_entity_id, nature)`**. Manual connections keep free-form **`nature`** values; the automatic taxonomy lives in **`backfield_entities.connections`**.

Revision **`046_agate_graph_description`** adds nullable-by-default **`description`** (`TEXT NOT NULL DEFAULT ''`) on **`agate_graph`** for optional flow summaries shown in Agate UI lists and on create/edit screens.

Revision **`047_substrate_article_fulltext`** adds Postgres GIN index **`idx_substrate_article_fulltext`** on `to_tsvector('english', coalesce(headline, '') || ' ' || coalesce(text, '') || ' ' || coalesce(url, ''))` for public article keyword search.

Revision **`048_location_h3`** enables Postgres extension **`h3`** (local image installs **`postgresql-16-h3`**), adds nullable **`h3_cell`** and **`h3_resolution`** on **`substrate_location`**, **`substrate_location_cache`**, and **`stylebook_location_canonical`**, and adds project-scoped H3 indexes on substrate location tables for map aggregation queries.

Revision **`025_backfield_ai_foundation`** adds shared **`backfield_ai_*`** tables for AI model configs, project overrides, default roles, and LLM call/cost records.

Revision **`026_org_integration_secret`** adds **`backfield_organization_integration_secret`** for encrypted organization-level integration credentials (AI provider keys first).

Revision **`030_ai_share_int_secret`** drops unique **`uq_bf_ai_model_integration_secret_id`** so several **`backfield_ai_model_config`** rows may reference one saved **`ai.credential.*`** secret.

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
  - organization integration lookups on `backfield_organization_integration_secret (organization_id)` plus unique `(organization_id, integration_key)`
  - AI model catalog lookup indexes on `backfield_ai_model_config (organization_id, status, model_kind)` and `(organization_id, provider, provider_model_id)`
  - AI call aggregation indexes on `backfield_ai_call_record (project_id, created_at)`, `(run_id, node_id)`, and `(run_id, status)`
  - GIST indexes on shared location geometry columns
- If a new query path matters for runtime behavior, capture the indexing decision in the migration or model change rather than leaving it implicit.

## Redesign space

- Prefer additive migrations early; rename columns via explicit migrations once naming stabilizes.
- When adding another app’s tables, use that app’s prefix and document it here.
