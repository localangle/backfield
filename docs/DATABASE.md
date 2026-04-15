# Database strategy (Backfield)

Backfield uses a **fresh schema**. Agate-owned tables use the **`agate_` prefix**; shared tenancy and project tables use **`backfield_`** so each app’s data is namespaced in Postgres (e.g. future Stylebook tables as `stylebook_*`).

## Ownership


| Area                                             | Owner                   | Notes                                    |
| ------------------------------------------------ | ----------------------- | ---------------------------------------- |
| Agate graphs, runs, templates                    | `packages/backfield-db` | Alembic migrations live here only        |
| Backfield orgs, users, projects, credentials     | `packages/backfield-db` | Same migration chain                     |
| Stylebook domain tables                          | future package / prefix | Add when Stylebook persistence is needed |


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

### Agate execution (`agate_*`)

- `agate_graph` — stored graph spec (JSON), FK to `backfield_project`.
- `agate_run` — execution record, status, result/error JSON.
- `agate_template` — curated template flows (`spec_json`); instantiated as new `agate_graph` rows.

### Secrets

- `backfield_project_secret` — per-project encrypted env-style secrets (`key` + `value_encrypted`); decrypted by the worker at run time when `MASTER_ENCRYPTION_KEY` is set.

Baseline revision `001_agate_baseline` creates initial `agate_*` tables and seed rows. Revision **`002_backfield_identity`** adds identity tables, renames `agate_project` → `backfield_project` (adds `organization_id`, optional `workspace_id`), and renames `agate_project_secret` → `backfield_project_secret`. Revision **`003_def_ws_general`** inserts the **Default Workspace** (`slug` `default`) and links General to it (org display name is seeded as **Backfield** in `002_backfield_identity`). Revision **`004_ws_membership`** adds `backfield_workspace_membership`.

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
- If a new query path matters for runtime behavior, capture the indexing decision in the migration or model change rather than leaving it implicit.

## Redesign space

- Prefer additive migrations early; rename columns via explicit migrations once naming stabilizes.
- When adding another app’s tables, use that app’s prefix and document it here.
