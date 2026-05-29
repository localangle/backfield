# Entity types and code layout

Backfield organizes persistence, catalog, API, and review code along two axes:

- **`content/`** — story carriers and run-scoped ingest context (article today; document later).
- **`entities/<type>/`** — Stylebook canonical domains and their substrate rows, mentions, and review surfaces.

Article is **content only**. It is not a Stylebook `EntityType` (see [`apps/stylebook-ui/src/lib/entityTypes.ts`](../apps/stylebook-ui/src/lib/entityTypes.ts)). Runtime flow and package boundaries are described in [`ARCHITECTURE.md`](ARCHITECTURE.md).

When adding a type or pipeline node, use [`.cursor/skills/add-entity-type/SKILL.md`](../.cursor/skills/add-entity-type/SKILL.md).

## Stylebook entity types

| Type | Slug (`EntityType`) | Status |
|------|---------------------|--------|
| Location | `location` | Full stack (substrate ingest, Stylebook canonical, review) |
| Person | `person` | UI stub; default **catalog_first** for new work |
| Organization | `organization` | UI stub; default **catalog_first** |
| Work | `work` | UI stub; default **catalog_first** |

Folder names in Python packages use these slugs (`location`, not `place`). Pipeline JSON may still use `places` in Geocode output; that is product vocabulary, not package naming.

## Templates for new types

### `full_stack`

Use when the type appears in **article text** and must round-trip through ingest, catalog, and (when needed) Agate review—like location today.

Includes:

- Database: `substrate_<entity>` (+ mentions/occurrences as needed), `stylebook_<entity>_canonical` (+ aliases/meta)
- `apps/worker/src/worker/substrate/entities/<type>/` and a hook from `substrate/orchestration.py`
- `packages/backfield-stylebook/src/backfield_stylebook/entities/<type>/` (Phase 03 target layout)
- `apps/stylebook-api/src/stylebook_api/entities/<type>/` (Phase 03)
- Optional: Agate node under `packages/backfield-agate/src/agate_nodes/`, `apps/agate-api/src/api/processed_item/entities/<type>/`

### `catalog_first`

Use when shipping **Stylebook catalog + API + UI** before extraction exists.

Includes:

- Stylebook tables, `backfield_stylebook/entities/<type>/`, stylebook-api router, `stylebook-ui` `entityConfigs/<type>.ts`
- Reserved `worker/substrate/entities/<type>/` stub (`__init__.py` with docstring only)
- **No** orchestration hook until a pipeline node persists the type
- **No** `processed_item` review package until product needs it

Default for **person**, **organization**, and **work** unless an extraction node ships in the same sprint.

## Directory conventions by layer

### Worker (current — Phase 02)

```
apps/worker/src/worker/
  substrate/
    __init__.py              # persist_from_consolidated, PersistResult, …
    orchestration.py
    common.py
    content/
      article.py
      geography_reset.py
    entities/
      location/
        upsert.py
        mentions.py
        span.py
      person/                # stub
      organization/        # stub
      work/                  # stub
    canonical/
      adjudication.py
  flags/
    replace_geography.py
  nodes/db_output.py
```

Public entrypoint: `from worker.substrate import persist_from_consolidated`

### backfield-stylebook (current)

```
packages/backfield-stylebook/src/backfield_stylebook/
  canonical/                 # policy, link, retrieval, slug, substrate_link_actions, …
  entities/
    location/
      persist.py
      types.py
  geocode_cache/             # fingerprint, resolve, sanity
```

Top-level shim modules (`canonical_policy.py`, `locations.py`, …) re-export from the new paths for one release; prefer `backfield_stylebook.canonical.*`, `entities.location.*`, and `geocode_cache.*` in new code.

### stylebook-api (current)

```
apps/stylebook-api/src/stylebook_api/
  entities/
    location/
      locations.py           # /v1/locations, saved places, …
      candidates.py          # /v1/candidates*
      meta.py                # canonical location meta
  routers/                   # health, stylebooks, geocode, imports, connections, …
```

HTTP paths are unchanged (`/v1/locations`, `/v1/candidates`, etc.).

### agate-api processed_item (current)

```
apps/agate-api/src/api/processed_item/
  __init__.py                  # re-exports for routers/runs.py
  content/
    article_context.py
  entities/
    location/
      locations_merge.py
      review_enrichment.py
  overlay/
    validate.py
    reviewed_output.py
  mention_occurrences.py       # shared until other entity mentions exist
```

Import via `api.processed_item` package or explicit submodules.

### Agate UI review library (current)

```
apps/agate-ui/src/lib/review/
  content/                   # article fields, tabs, display title, source label, evidence spans
  entities/
    location/                # place geometry, edit fields, mention occurrences, review row helpers
  overlay/
    verificationOverlay.ts   # overlay state for verification tab
```

React components under `src/components/ProcessedItem*` keep their names; they import from `@/lib/review/…`.

### Agate nodes

One folder per node under `packages/backfield-agate/src/agate_nodes/<snake_case>/`:

- `node.py` (or `node_port.py` / `runner.py`)
- `metadata.json`
- `ui/` (React panels)
- `prompts/` when LLM-backed

`db_output` stays the generic persist node; entity logic lives in worker `substrate/`.

Panel layout, tabs, typography, sync workflow, and shared helpers are documented in [`FRONTEND.md` → Agate nodes and node panels](FRONTEND.md#agate-nodes-and-node-panels).

## Layer checklist

| Layer | full_stack | catalog_first | Typical paths |
|-------|------------|---------------|---------------|
| Database | Substrate + mention tables + canonical tables | Canonical (+ connections) only | `packages/backfield-db`, Alembic |
| backfield-stylebook | `entities/<type>/` | Same | `packages/backfield-stylebook/src/backfield_stylebook/` |
| Worker | `substrate/entities/<type>/` + `orchestration.py` hook | Stub package only | `apps/worker/src/worker/substrate/` |
| stylebook-api | `entities/<type>/` router | Same | `apps/stylebook-api/src/stylebook_api/` |
| stylebook-ui | `entityConfigs/<type>.ts` | Same | `apps/stylebook-ui/src/lib/entityConfigs/` |
| Agate nodes | New node folder | Skip | `packages/backfield-agate/src/agate_nodes/` |
| agate-api review | `processed_item/entities/<type>/` | Skip until review needed | `apps/agate-api/src/api/processed_item/` |
| Tests | Per layer | Per layer | `tests/worker/`, `tests/stylebook/`, `tests/stylebook_api/`, `tests/agate_api/` |
| Docs | `DATABASE.md`, `API.md`, `FRONTEND.md`, this file | Same | `docs/` |

## Naming rules

- **Python package folders:** `location`, `person`, `organization`, `work` (match `EntityType`).
- **Database tables:** Do not rename `substrate_*` or `stylebook_location_*` in layout-only refactors.
- **Filenames inside typed packages:** Avoid `substrate_` and `processed_item_` prefixes; the directory is the namespace (`upsert.py`, not `substrate_location.py`).
- **Pipeline / review JSON:** May keep legacy keys (`places`, etc.); do not rename product payloads in organization refactors.

## Import and re-export policy

| Package | Policy |
|---------|--------|
| **worker** | Few external importers; update call sites in the same PR as file moves. Public API: `worker.substrate` package `__init__.py`. |
| **backfield-stylebook** | **Shim modules** at legacy top-level names (`canonical_policy.py`, `locations.py`, …) re-export from `canonical/`, `entities/location/`, and `geocode_cache/`. Package `__init__.py` uses new paths. Prefer new paths in new code. |
| **stylebook-api / agate-api** | Update router imports and tests; **no HTTP URL changes** in layout phases. |

## Validation

After any layer change:

```bash
make lint
make test
```

Run `make smoke` when runtime behavior across services changes.
