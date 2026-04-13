# Database strategy (Backfield)

Backfield uses a **fresh schema**. Agate-owned tables use the `**agate_` prefix** so each app’s data is namespaced in Postgres (e.g. future Stylebook tables as `stylebook_`*).

## Ownership


| Area                                             | Owner                   | Notes                                    |
| ------------------------------------------------ | ----------------------- | ---------------------------------------- |
| Agate graphs, runs, projects, templates, secrets | `packages/backfield-db` | Alembic migrations live here only        |
| Stylebook domain tables                          | future package / prefix | Add when Stylebook persistence is needed |


Do **not** run multiple services that each invoke `alembic upgrade` on startup for the same revision path; pick one migration runner (e.g. `agate-api` on deploy, or `make migrate`).

## Current tables (Agate)

- `agate_project` — projects (name, slug, optional `settings_json` for UI metadata such as `system_prompt`).
- `agate_graph` — stored graph spec (JSON), FK to `agate_project`.
- `agate_run` — execution record, status, result/error JSON.
- `agate_template` — curated template flows (`spec_json`); instantiated as new `agate_graph` rows.
- `agate_project_secret` — per-project encrypted env-style secrets (`key` + `value_encrypted`); decrypted by the worker at run time when `MASTER_ENCRYPTION_KEY` is set.

Schema is defined by a single baseline revision, `001_agate_baseline`, which creates the `agate_`* tables and seed rows (General project, Geocode pipeline template).

**Existing databases** that already applied the old `001`–`004` chain: if the live schema already matches the `agate_`* layout above, point `alembic_version` at the new head. Alembic cannot `stamp` from a revision id that no longer exists in the repo, so use SQL once:

```sql
UPDATE alembic_version SET version_num = '001_agate_baseline';
```

(If your table uses multiple-version rows, replace them with a single row for `001_agate_baseline` per your Alembic setup.) Otherwise reset the database (`make reset-db` + `make up`) or rebuild from a dump.

## Indexing expectations

- Tables must stay namespaced by owning app prefix.
- Add indexes for expected lookup, join, and filter paths as part of the schema change.
- Existing intentional indexes include:
  - `agate_project.slug`
  - `agate_run.graph_id`
  - `agate_project_secret.project_id`
  - unique key on `agate_project_secret (project_id, key)`
- If a new query path matters for runtime behavior, capture the indexing decision in the migration or model change rather than leaving it implicit.

## Redesign space

- Prefer additive migrations early; rename columns via explicit migrations once naming stabilizes.
- When adding another app’s tables, use that app’s prefix and document it here.

