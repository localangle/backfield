# Entity types and code layout

Backfield organizes persistence, catalog, API, and review code along two axes:

- **`content/`** — story carriers and run-scoped ingest context (article today; document later).
- **`entities/<type>/`** — Stylebook canonical domains and their substrate rows, mentions, and review surfaces.

Article is **content only**. It is not a Stylebook `EntityType` (see [`apps/stylebook-ui/src/lib/entityTypes.ts`](../apps/stylebook-ui/src/lib/entityTypes.ts)). Runtime flow and package boundaries are described in [`ARCHITECTURE.md`](ARCHITECTURE.md).

When adding a type, use [`.cursor/skills/add-entity-type/SKILL.md`](../.cursor/skills/add-entity-type/SKILL.md) — an interactive interview that produces `prd/<slug>/prd.md` and implementation issues.

## Stylebook entity types

| Type | Slug (`EntityType`) | Status |
|------|---------------------|--------|
| Location | `location` | Full stack (substrate ingest, Stylebook canonical, review) |
| Person | `person` | Full stack including PersonExtract node and Agate people review tab |
| Organization | `organization` | Stub — planned via add-entity-type skill |
| Work | `work` | Stub — planned via add-entity-type skill |

Folder names in Python packages use these slugs (`location`, not `place`). Pipeline JSON may still use `places` in Geocode output; that is product vocabulary, not package naming.

Registry source of truth: `packages/backfield-stylebook/src/backfield_stylebook/entity_types.py`.

## Issue 00 — shared foundation

Before adding a new type, ensure **Issue 00** scaffolding is merged:

| Marker | Path |
|--------|------|
| Entity registry + fingerprint | `backfield_stylebook/entity_types.py` |
| Persist domain dispatch | `worker/substrate/entities/registry.py` |
| Shared field docs | `docs/DATABASE.md` → **Shared entity fields** |
| UI entity registry | `apps/stylebook-ui/src/lib/entityRegistry.ts` |

Foundation is **refactor-only**: no new entity tables; location behavior unchanged.

## Adding a new type (default pipeline)

**Profile:** `extract_and_persist` — always include an extract node in the plan.

```
TextInput → <Type>Extract → DBOutput → substrate → Stylebook
```

**Location exception:** `PlaceExtract → GeocodeAgent → DBOutput` (enrichment node is location-only).

**Agate review** is always in the plan as a **late issue** (after extract + ingest smoke).

### Consolidated JSON keys

Keys follow **`EntityType` slug** pluralization (not Agate tab names):

| Slug | Consolidated key |
|------|------------------|
| `location` | `places` (legacy) |
| `person` | `people` |
| `organization` | `organizations` |
| `work` | `works` |

### Canonical ID policy

All **new** canonical types use **UUID string** primary keys from day one.

### Per-type issue order

| Issue | Slice |
|-------|-------|
| 01 | Type-specific schema (migration) |
| 02 | `backfield_stylebook/entities/<type>/` |
| 03 | stylebook-api + stylebook-ui |
| 04 | Worker substrate + orchestration handler |
| 05 | `<Type>Extract` node + smoke graph |
| 06 | Agate review tab |

See [`DATABASE.md`](DATABASE.md) for shared substrate and Stylebook column contracts.

## Directory conventions by layer

### Worker (current)

```
apps/worker/src/worker/
  substrate/
    __init__.py
    orchestration.py
    entities/
      registry.py            # PersistDomainHandler dispatch
      location/
        handler.py           # places persist loop
        upsert.py
        mentions.py
        span.py
      person/
        handler.py           # people persist loop
        upsert.py
        mentions.py
      organization/          # stub
      work/                  # stub
    canonical/
      adjudication.py
  nodes/db_output.py
```

Public entrypoint: `from worker.substrate import persist_from_consolidated`

### backfield-stylebook (current)

```
packages/backfield-stylebook/src/backfield_stylebook/
  entity_types.py            # slug registry, consolidated keys, fingerprint
  canonical/
  entities/
    location/
      persist.py
      types.py
  geocode_cache/
```

### stylebook-api (current)

```
apps/stylebook-api/src/stylebook_api/
  helpers/
    project_scope.py
    pagination.py
  entities/
    location/
      locations.py           # /v1/locations (unchanged)
      candidates.py          # /v1/candidates*
      meta.py
```

Location HTTP paths are unchanged. Future types use `/v1/<plural>`, `/v1/<plural>/candidates`, meta under canonical id — see [`API.md`](API.md).

### Stylebook canonical detail page (all entity types)

Every Stylebook **canonical detail** page (`/stylebook/{slug}/<type>/canonical/{id}`) must expose the same evidence + catalog sections as location (adapt labels and columns per type):

| Section | Scope | API (stylebook-scoped) |
|---------|--------|-------------------------|
| **Details** | Canonical card fields | `GET\|PATCH\|DELETE …/canonical-<type>/{id}` |
| **Mentions** | Grouped by linked substrate row; respects `?project=` filter | `GET …/canonical-<type>/{id}/mentions`, `GET …/linked-substrates` |
| **Metadata** | Stylebook-wide JSON meta on the canonical | `GET\|POST …/meta`, `PATCH\|DELETE …/meta/{meta_id}` |
| **Connections** | Stylebook-wide graph edges | `GET\|POST …/connections`, … |

UI wiring: reuse **`MetaTab`** via a thin `<Type>MetaTab` wrapper; mentions table mirrors `LocationDetail` (substrate group header with **Move…** / **Unlink**, nested article rows with nature, role, quoted text). Location adds **Geography**; non-location types omit map sections unless the entity has geography.

When adding a type (issue 03), ship mentions list route + linked-substrates + meta routes together with the detail page — do not leave metadata or mentions for a follow-up unless the type is catalog-only stub.

### stylebook-ui (current)

```
apps/stylebook-ui/src/lib/
  entityTypes.ts
  entityRegistry.ts          # EntityConfig + home cards
  entityConfigs/
    connectionPickers.ts
```

Location catalog pages remain under `src/pages/Locations*.tsx`; per-type issues add config-driven surfaces.

### agate-api processed_item (current)

```
apps/agate-api/src/api/processed_item/
  entities/
    location/
  overlay/
  mention_occurrences.py
```

### Agate UI review library (current)

```
apps/agate-ui/src/lib/review/
  entities/
    location/
```

Non-location tabs: **People** review is implemented (issue 06); other entity tabs remain placeholders.

### Agate nodes

One folder per node under `packages/backfield-agate/src/agate_nodes/<snake_case>/`.

Current extract nodes: `place_extract`, `person_extract`. Run `npm run sync-nodes` in `apps/agate-ui` after adding or changing node UI/metadata.

For **run AI cost and step labels**, the worker records React Flow `node_id` and node type on each `backfield_ai_call_record` row; Agate UI shows user-facing names from synced `metadata.json` `label` (via `getNodeStepDisplayName`, with `node_type` fallback when the graph id is missing). New extract nodes must ship `metadata.json` with a product **`label`** before merge.

**Extract prompt layout (`prompts/extract.md`):** Put static instructions, field rules, and output-format guidance **before** the article body. End the file with a `## Text to Analyze` section containing only the `{text}` placeholder (same pattern as `place_extract`). The opening paragraph should refer to “the text provided at the end of this prompt” so the model knows where to look. This keeps the long static prefix identical across requests so provider prompt caches can reuse it; only the trailing article text changes per run.

`db_output` stays the generic persist node; entity logic lives in worker `substrate/`.

## Naming rules

- **Python package folders:** `location`, `person`, `organization`, `work` (match `EntityType`).
- **Database tables:** Do not rename `substrate_*` or `stylebook_location_*` in layout-only refactors.
- **Pipeline / review JSON:** May keep legacy keys (`places`, etc.).

## Validation

```bash
make lint
make test
```

Run `make smoke` when runtime behavior across services changes.
