# Database strategy (Backfield)

Backfield uses a **fresh schema**. Agate-owned tables use the **`agate_` prefix**. Cross-app **infrastructure** (orgs, users, projects, credentials) uses **`backfield_`**. The shared **content/location substrate** uses **`substrate_`** (articles, locations, mentions, occurrences, cache). Editorial Stylebook tables will use `stylebook_*`.

## Ownership


| Area                                             | Owner                   | Notes                                                                  |
| ------------------------------------------------ | ----------------------- | ---------------------------------------------------------------------- |
| Agate graphs, runs, templates                    | `packages/backfield-db` | Alembic migrations live here only                                      |
| Backfield orgs, users, projects, credentials     | `packages/backfield-db` | Same migration chain                                                   |
| Shared content/location substrate                | `packages/backfield-db` | `substrate_article`, `substrate_location`, mentions, occurrences, cache |
| Stylebook editorial/canonicalization tables      | future package / prefix | Layer on top of shared substrate when canonical management lands        |


Do **not** run multiple services that each invoke `alembic upgrade` on startup for the same revision path; pick **one** migration runner (the `agate-api` entrypoint on deploy, or `make migrate` locally).

## Current tables

### Identity and projects (`backfield_*`)

- `backfield_organization` — tenant; migration seeds a `default` org for single-org installs.
- `backfield_workspace` — optional sub-org grouping under an organization (generic naming; many projects per workspace). Revision **`003_def_ws_general`** seeds a **`default`** workspace under the **`default`** org and sets the **General** project’s `workspace_id` to that row (so General lives under Organization → Workspace → Project).
- `backfield_user` — user identity (email, password hash, `disabled_at`).
- `backfield_organization_membership` — `(user_id, organization_id)` with `role` (`org_admin`, `member`, …).
- `backfield_project` — canonical project for Agate graphs, encrypted vault keys, Stylebook scoping, and future Core import APIs (`organization_id` required; `workspace_id` optional but new/bootstrap flows should set it).
- `backfield_workspace_membership` — `(user_id, workspace_id)` unique; grants a **member** access to every project whose `workspace_id` is that workspace (same org). Unioned in auth with legacy `backfield_project_membership` rows until the latter are fully deprecated.
- `backfield_project_membership` — `(user_id, project_id)` with optional per-project `role` (legacy explicit grants).
- `backfield_api_credential` — per-project API keys (`credential_type` `user` or `service`), `key_prefix` + `key_hash`, `revoked_at`.

### Shared content and locations (`substrate_*`)

- `substrate_article` — project-scoped content item for stateful ingestion. Uses a project-scoped external identity hierarchy with `(project_id, url)` as the fallback uniqueness rule. `source_run_id` stores the executing `agate_run.id` (UUID string) when the row is produced from an Agate worker run.
- `substrate_image` — images attached to a `substrate_article`.
- `substrate_location` — durable shared location entity row. Stores normalized naming, provider identity/fingerprint, canonical status fields, and PostGIS geometry.
- `substrate_location_mention` — one aggregate article-to-location association per `(article_id, location_id)` with workflow state, provenance, `role_in_story`, primary **`nature`** (PlaceExtract editorial role: `primary`, `secondary`, `subject`, `context`, `person`, `unknown`), and optional **`nature_secondary_tags_json`** for extra roles.
- `substrate_location_mention_occurrence` — supporting evidence rows for a location mention aggregate (`mention_text`, offsets, labels, provenance). Editorial prose lives on the mention (`role_in_story`, `description` from extraction) — not duplicated here.
- `substrate_location_cache` — project-scoped dumb cache of external resolution results only. Cache rows are lookup accelerators, not the durable entity identity layer.

### Agate execution (`agate_*`)

- `agate_graph` — stored graph spec (JSON), FK to `backfield_project`.
- `agate_run` — execution record, status, result/error JSON.
- `agate_template` — curated template flows (`spec_json`); instantiated as new `agate_graph` rows.

Schema revisions start at `001_agate_baseline` (initial `agate_*` tables and seed rows). Revision **`002_backfield_identity`** adds identity tables, renames `agate_project` → `backfield_project` (adds `organization_id`, optional `workspace_id`), and renames `agate_project_secret` → `backfield_project_secret`. Revision **`002_starter_flow_layout`** (runs next) is a **data migration** that rewrites stored `spec_json` for graphs named `Starter flow` (and the seeded **Geocode pipeline** template) so node positions match the UI card widths—run `make migrate` so existing databases pick up the layout fix.

### Secrets

- `backfield_project_secret` — per-project encrypted env-style secrets (`key` + `value_encrypted`); decrypted by the worker at run time when `MASTER_ENCRYPTION_KEY` is set.

Revision **`003_def_ws_general`** inserts the **Default Workspace** (`slug` `default`) and links General to it (org display name is seeded as **Backfield** in `002_backfield_identity`). Revision **`004_ws_membership`** adds `backfield_workspace_membership`. Revision **`005_location_schema_foundation`** introduces the shared content/location substrate under historical `backfield_*` table names (since renamed—see **`009_rename_substrate_tables`**) and enables PostGIS for location geometry. Revision **`006_article_source_run_id_text`** aligns article `source_run_id` with string `agate_run.id` values (and adds the ORM-level foreign key).

Revision **`007_starter_flow_add_db_output`** rewrites stored **Starter flow** `agate_graph.spec_json` rows to the canonical starter spec that includes **`DBOutput`** (so local stacks pick up persistence gating without manual graph edits).

Revision **`008_drop_occurrence_context_text`** drops **`context_text`** from the location mention occurrence table (redundant with extraction `description` / mention fields). Revision **`009_rename_substrate_tables`** renames substrate tables and related indexes/constraints from `backfield_*` to **`substrate_*`** so `backfield_*` stays reserved for tenancy and infrastructure.

The **Starter flow** graph row for the General project is created at runtime when `BACKFIELD_LOCAL_BOOTSTRAP=1` on `agate-api` startup (see [docs/OPERATIONS.md](OPERATIONS.md)), not by the baseline migration alone.

**Existing databases** that already applied older revisions: follow migration notes in your upgrade path or reset (`make reset-db` + `make up`) for dev.

## Indexing expectations

- Tables must stay namespaced by owning app prefix.
- Add indexes for expected lookup, join, and filter paths as part of the schema change.
- Intentional indexes include:
  - `backfield_project.slug`
  - `agate_run.graph_id`
  - `backfield_project_secret.project_id`
  - unique key on `backfield_project_secret (project_id, key)`
  - GIST indexes on shared location geometry columns
- If a new query path matters for runtime behavior, capture the indexing decision in the migration or model change rather than leaving it implicit.

## Redesign space

- Prefer additive migrations early; rename columns via explicit migrations once naming stabilizes.
- When adding another app’s tables, use that app’s prefix and document it here.
