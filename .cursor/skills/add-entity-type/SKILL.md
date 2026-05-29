---
name: add-entity-type
description: >-
  Add a Stylebook canonical entity type (location-style full stack or catalog-first)
  or a new Agate pipeline node. Use when adding person, organization, work, substrate
  ingest, Stylebook API routes, or agate_nodes folders. Read docs/ENTITY_TYPES.md first.
---

# Add entity type (or pipeline node)

Use this skill when adding a **canonical entity type** (person, organization, work, or extending location patterns) or when adding a **pipeline node** that persists to substrate.

## Read first

1. [`docs/ENTITY_TYPES.md`](../../docs/ENTITY_TYPES.md) — axes, templates, paths, checklist
2. [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) — runtime and package boundaries
3. Local planning archive (optional): `prd/organization-refactor/decisions.md`
4. For behavior parity: **agate-ai-platform** sibling repo (`/Users/cjdd3b/apps/agate-ai-platform`) — copy-then-adapt per `AGENTS.md`

## Choose a template

| Template | When |
|----------|------|
| **`full_stack`** | Type appears in article text and must round-trip: extract → geocode/resolve → DBOutput → substrate → Stylebook canonical → optional Agate review |
| **`catalog_first`** | Catalog, API, and UI ship **before** extraction; no worker orchestration until a node exists |

**Default** for person / organization / work: **`catalog_first`** unless an extraction node ships in the **same sprint**.

---

## `full_stack` checklist

Replace `<type>` with `location`, `person`, `organization`, or `work`.

### 1. Database

- Add SQLModel models and Alembic migration in `packages/backfield-db`
- Tables typically: `substrate_<type>`, mention/occurrence tables as needed, `stylebook_<type>_canonical`, aliases/meta
- Update [`docs/DATABASE.md`](../../docs/DATABASE.md)
- Follow [backfield-db-change](../../.cursor/skills/backfield-db-change/SKILL.md) if schema is non-trivial

### 2. backfield-stylebook

- Add `packages/backfield-stylebook/src/backfield_stylebook/entities/<type>/` (persist, types)
- Reuse shared logic under `canonical/` (policy, link, retrieval, substrate_link_actions)
- Geocode cache (location today): `geocode_cache/` (fingerprint, resolve, sanity)

**Location reference:**

| Concern | Path |
|---------|------|
| Persist / link | `entities/location/persist.py` |
| PlaceExtract types | `entities/location/types.py` |
| Policy | `canonical/policy.py` |

Legacy imports (`locations`, `canonical_policy`, …) work via shim modules; prefer new paths in new code.

### 3. Worker substrate

- Implement `apps/worker/src/worker/substrate/entities/<type>/` (`upsert.py`, `mentions.py`, `span.py` as needed)
- Hook from `apps/worker/src/worker/substrate/orchestration.py` after article sync (mirror location loop over consolidated output)
- Public API stays on `from worker.substrate import persist_from_consolidated`

**Location reference (current):**

| Module | Path |
|--------|------|
| Orchestration | `substrate/orchestration.py` |
| Article | `substrate/content/article.py` |
| Geography reset | `substrate/content/geography_reset.py` |
| Location upsert | `substrate/entities/location/upsert.py` |
| Mentions | `substrate/entities/location/mentions.py` |
| Span matching | `substrate/entities/location/span.py` |
| Canonical LLM adjudication | `substrate/canonical/adjudication.py` |

### 4. stylebook-api

- Add `apps/stylebook-api/src/stylebook_api/entities/<type>/` (router modules + `main.py` mount)
- Document URLs in [`docs/API.md`](../../docs/API.md); do not change existing path prefixes when reorganizing modules

**Location reference:** `entities/location/locations.py`, `candidates.py`, `meta.py`

### 5. stylebook-ui

- Add or extend `apps/stylebook-ui/src/lib/entityConfigs/<type>.ts`
- User-facing copy: non-technical language per [`docs/FRONTEND.md`](../../docs/FRONTEND.md)
- Register routes in entity config; wire connection pickers in `entityConfigs/connectionPickers.ts` if needed

### 6. Agate pipeline (when extracting from text)

- New folder: `packages/backfield-agate/src/agate_nodes/<node_name>/`
  - `metadata.json`, `node.py`, `ui/`, optional `prompts/`
- Reference: [`place_extract`](../../packages/backfield-agate/src/agate_nodes/place_extract/), [`geocode_agent`](../../packages/backfield-agate/src/agate_nodes/geocode_agent/)
- Persist via existing [`db_output`](../../apps/worker/src/worker/nodes/db_output.py) node calling `worker.substrate.persist_from_consolidated`

### 7. agate-api review (when product needs review UI)

- Add `apps/agate-api/src/api/processed_item/entities/<type>/` (merge, enrichment modules)
- Re-export from `api/processed_item/__init__.py` if `routers/runs.py` should use package imports
- Update `tests/agate_api/`

**Location reference:**

| Concern | Path |
|---------|------|
| Article context | `content/article_context.py` |
| Location merge | `entities/location/locations_merge.py` |
| Review enrichment | `entities/location/review_enrichment.py` |
| Overlay validate | `overlay/validate.py` |
| Reviewed output | `overlay/reviewed_output.py` |
| Mention occurrences (shared) | `mention_occurrences.py` |

### 8. Tests and docs

- `tests/worker/`, `tests/stylebook/`, `tests/stylebook_api/`, `tests/agate_api/` as applicable
- Update `ENTITY_TYPES.md`, `API.md`, `FRONTEND.md`, `ARCHITECTURE.md`

---

## `catalog_first` checklist

1. Database: canonical (+ alias) tables; connections if needed — **no** substrate ingest tables yet unless product requires placeholders
2. `backfield_stylebook/entities/<type>/`
3. `stylebook_api/entities/<type>/` + tests
4. `stylebook-ui` `entityConfigs/<type>.ts` — stubs exist for person/org/work in `entityTypes.ts`
5. `stylebook_api/imports/registry.py` — register import handlers when imports ship
6. Worker: add **stub only** — `apps/worker/src/worker/substrate/entities/<type>/__init__.py` (docstring pointing to `docs/ENTITY_TYPES.md`)
7. **Skip** orchestration hook, Agate extract nodes, `processed_item` review until full_stack phase
8. Tests + docs for catalog/API/UI layers only

---

## Add a pipeline node only (no new entity type)

When adding a node that does **not** introduce a new Stylebook `EntityType`:

1. Create `packages/backfield-agate/src/agate_nodes/<snake_case_name>/` with `metadata.json`, `node.py`, `ui/`
2. Put panel/node React components under `ui/` in that package folder — **not** under `apps/agate-ui/src/nodes/`. Run `npm run sync-nodes` in `apps/agate-ui` to copy UI into the app and regenerate `src/nodes/registry.ts`.
3. If the node writes to Postgres substrate, ensure graph output shape matches what `substrate/orchestration.py` expects, or extend orchestration deliberately (separate change)
4. `db_output` remains the standard persist node for consolidated `places` (location domain today)

---

## Validation

```bash
make lint
make test
```

After cross-service runtime changes:

```bash
make smoke
```

Focus tests by layer (see `docs/TESTING.md`).

---

## Agate UI review (when product needs review for a type)

- Add `apps/agate-ui/src/lib/review/entities/<type>/` (mirror location modules)
- Keep shared article/overlay helpers in `review/content/` and `review/overlay/`
- See `docs/FRONTEND.md` → **Agate UI review library**

**Location reference:** `review/entities/location/placeGeometry.ts`, `placeEditFields.ts`, `mentionOccurrences.ts`, `reviewRow.ts`

---

## Organization refactor status

Phases **01–04** and **06** (layout only) are complete in the repo. **Phase 05** (first new canonical type) is product-driven and out of scope for the layout initiative. Expand this skill when implementing a new type—not as part of the refactor closure.
