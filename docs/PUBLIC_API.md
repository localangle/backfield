# Public API

Design reference for Backfield’s **consumer-facing HTTP surface**. This document is the source of truth for organizing principles, URL layout, and rollout phases. Implementation lives in **`apps/core-api`** under **`/public/v1`**.

For internal editorial routes (Stylebook UI, candidate review, Agate runs with review overlay), see [`API.md`](API.md). For package boundaries, see [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Goals

- One **physical public API** on Core API that queries substrate and Stylebook data together.
- **Clean, consistent** routes and parameters across canonical entity types.
- Clear separation between **public**, **app/editorial**, **platform/admin**, and **utility** endpoints.
- **Read-only** query surface to start, plus a controlled **run trigger** for automation.
- Documentation that another agent can turn into an external docs site (OpenAPI + reference markdown).

## Non-goals (v1)

- Parity with any prior platform’s public routes — design for Backfield’s current schema and services.
- Full article body text in public responses.
- Public writes to Stylebook canonicals, candidate actions, or review overlay.
- Public graph editing, project admin, or org admin.

---

## Endpoint taxonomy

| Tier | Prefix / location | Auth | Purpose |
|------|-------------------|------|---------|
| **Public** | Core API **`/public/v1`** | Project API key (`bfk_…`) | Stable read queries + run trigger |
| **App / editorial** | Stylebook API `/v1`, Agate API `/v1` | Session cookie | UI workflows: canonical CRUD, candidates, review, imports |
| **Platform / admin** | Core API `/v1` (non-public) | Session or service token | Auth, org admin, AI catalog, credentials |
| **Utility** | `/health`, node metadata, runtime geocode | Varies | Ops and worker/runtime helpers — not part of public docs |

Only **`/public/v1`** routes belong in the external Public API Reference. Everything else is internal unless explicitly promoted later.

---

## Physical layout

All public routes are served by **`apps/core-api`** (port **8004** locally). Agate API and Stylebook API remain internal/editorial services; they are not alternate public hostnames.

Shared query and serialization logic should live in **`packages/backfield-entities`** (or a small sibling package if the surface grows large), not duplicated in routers. Routers validate auth, parse parameters, and call shared services.

```mermaid
flowchart LR
    Client[PublicClient] -->|Bearer bfk| CoreAPI[core-api /public/v1]
    CoreAPI --> Entities[backfield-entities query layer]
    Entities --> Postgres[(Postgres)]
    CoreAPI -->|run enqueue only| Redis[Redis / Celery]
```

---

## Authentication and authorization

- **Mechanism:** `Authorization: Bearer <project_api_key>` (keys issued via Core API credentials routes; prefix `bfk_`).
- **Scope:** Every public route is **project-scoped**. The key must grant access to the project in the URL (same rules as `backfield_auth.gate` project access).
- **No session cookies** on public routes.
- **Service token** (`SERVICE_API_TOKEN`) is for internal automation only — not documented as a public consumer credential.

---

## URL conventions

### Project scope

All public resources are nested under the project:

```text
/public/v1/projects/{project_slug}/…
```

`project_slug` resolves to `backfield_project`. Stylebook catalog resolution (workspace default Stylebook) is **internal** — callers do not pass `stylebook_slug` on public routes.

### Resource naming

- Use **plural product nouns** in paths: `articles`, `locations`, `people`, `organizations`, `works`, `custom-records`.
- Canonical entity ids are **UUID strings** in path segments.
- Article ids are **integers** (`substrate_article.id`).

### Query modes (per canonical type)

Each canonical type supports a **shared spine** plus type-specific filters:

| Mode | HTTP | Path pattern | Shared parameters |
|------|------|--------------|-------------------|
| **Keyword** | `GET` | `…/{type}/search` | `q`, `limit`, `offset`, type filters |
| **Entity** | `GET` | `…/{type}/{id}` | — |
| **Entity evidence** | `GET` | `…/{type}/{id}/mentions` | `limit`, `offset`, article filters |
| **Entity graph** | `GET` | `…/{type}/{id}/connections` | optional `nature`, pagination |
| **Semantic** | `POST` | `…/{type}/semantic-search` | JSON body: `query`, evidence filters |
| **Geography** | `GET` | `…/geo/…` and geo filters on search/mentions | bbox, `location_type`, `canonical_id` |

**Locations** get the richest geography surface (types list, search by type, bbox, mentions near a place). **People** and **organizations** expose geography mainly through mention/article filters (e.g. articles mentioning entities linked to a location). **Works** follow the same spine when the type is implemented.

Type-specific filter examples (non-exhaustive):

| Type | Extra keyword / list filters |
|------|------------------------------|
| Locations | `location_type`, formatted address tokens |
| People | `person_type`, `public_figure`, `title`, `affiliation` |
| Organizations | `organization_type` |
| Works | TBD when type ships |

### Pagination and sorting

- **Lists and search:** `limit` (default 25, max 100 unless noted) and `offset` (default 0).
- **Response envelope:**

```json
{
  "items": [],
  "pagination": {
    "limit": 25,
    "offset": 0,
    "total": 0
  }
}
```

- **Sort:** optional `sort` query param per resource; document allowed values per route. Default sort is stable and type-appropriate (e.g. label ascending for canonical lists, recency for mentions).

### Errors

Follow FastAPI conventions. Public routes use consistent JSON error bodies:

```json
{ "detail": "Human-readable message" }
```

- **404** when the project, article, or canonical is missing or outside the caller’s project scope (do not leak cross-project existence).
- **403** when the API key lacks project access.
- **503** when semantic search is requested but no embedding model is configured.

---

## Articles

Articles are first-class public resources (`substrate_article` + related meta). Related evidence (mentions, geography, custom records, images) uses an **article hub** layout: lean detail plus **paginated sub-routes** per slice—not a single mega-endpoint with combinatorial `include` flags.

### Article hub (organizing principle)

| Layer | Pattern | Use when |
|-------|---------|----------|
| **Detail** | `GET …/articles/{article_id}` | Headline, metadata, preview; optional cheap **`include=counts`** |
| **Sub-routes** | `GET …/articles/{article_id}/<slice>` | Heavy or paginated data: mentions, locations, custom records, images |
| **Entity-centric** | `GET …/people/{id}/mentions`, etc. | Starting from a canonical, not a story |
| **Bundle (later)** | `GET …/articles/{article_id}/bundle?sections=…` | Optional one-round-trip aggregator; not the primary contract |

Do **not** use open-ended `?include=locations,people,custom_records,images` on detail—payload size, pagination, and caching differ too much per slice. Reserve `include` on detail for **small** embeds only (`counts`).

### Detail (`GET …/articles/{article_id}`)

**Core fields (v1):**

- `id`, `headline`, `url`, `author`, `pub_date`, `external_source`, `external_id`, `entry_id`
- **`metadata`**: tags from `substrate_article_meta` (`meta_type`, `category`, `confidence`, …)
- Optional **`preview`**: short truncated snippet (max 280 characters; not full body)

**Query:** `include_preview` (default `true`).

**Optional embed:** `include=counts` adds cheap aggregates without loading evidence:

```json
{
  "entity_counts": { "locations": 4, "people": 2, "organizations": 1 },
  "custom_record_counts": { "contracts": 3 },
  "image_count": 2
}
```

### Excluded from detail

- Full **`text`** / body
- Mention rows, geometry, custom record payloads, image payloads (use sub-routes)
- Internal provenance (`source_run_id`, overlay state, …) unless a support contract requires them

### Article sub-routes (primary pattern for rich context)

All paths are under `…/projects/{project_slug}/articles/{article_id}/…`. Shared pagination: `limit`, `offset`. Returns **404** when the article is missing or not in the project.

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `…/mentions` | Paginated mention evidence across entity types |
| `GET` | `…/locations` | Geography-focused: places in the story with canonical + geometry where available |
| `GET` | `…/custom-records` | Custom Extract rows for this article |
| `GET` | `…/images` | Images attached to the article (`substrate_image`) |

**`GET …/mentions`** — unified index for “who/what is mentioned?”

- Query: `entity_type` optional filter (`location`, `person`, `organization`)
- Each row: entity type, substrate/canonical ids, label, mention text/quote spans, optional canonical summary
- Paginated; does not return full article body

**`GET …/locations`** — map-oriented view (may overlap mentions but different shape)

- Resolved Stylebook canonical fields where linked
- Geometry / formatted address when present
- Paginated list of location mentions or deduplicated places (exact dedupe rules documented at ship time)

**`GET …/custom-records`** — see [Custom records](#custom-records) (same response shape as project search, scoped to one article).

**`GET …/images`** — `image_id`, `url`, `caption` from `substrate_image`.

**Future (non-primary):** `GET …/bundle?sections=locations,custom_records,images` composes the above for clients that need one round trip; implemented as a thin aggregator over sub-route query helpers.

### Article list / search

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `…/articles/search` | Keyword search + metadata filters + date range |
| `GET` | `…/articles/{article_id}` | Article detail |

**Search parameters:**

- `q` — keyword (headline, URL)
- `meta_type`, `meta_category` — filter on `substrate_article_meta`
- `pub_date_from`, `pub_date_to` — ISO dates (`YYYY-MM-DD`)
- Standard pagination
- `include_preview` (default `false` on search)

### Two valid entry points

- **Story-first:** article detail → sub-routes (`/articles/{id}/mentions`, …)
- **Entity-first:** canonical detail → `/people/{id}/mentions` (etc.)

Sub-routes and entity-centric routes share query helpers in `backfield-entities`; only URL shape and default filters differ.

---

## Canonical entities (Stylebook + substrate)

Public responses expose the **resolved editorial view**: Stylebook canonical fields, mention counts, and evidence rows joined from substrate — not open candidate queues or raw ingest policy blobs.

### Shared detail shape (conceptual)

- Canonical identity: `id`, `slug`, `label`, type-specific fields
- **`mention_count`** (project scope, non-deleted mentions)
- Links to **Stylebook meta** and **connections** where applicable

### Routes (per type `{type}` = `locations` | `people` | `organizations` | `works`)

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `…/{type}/search` | Keyword / filter search |
| `GET` | `…/{type}/{id}` | Canonical detail |
| `GET` | `…/{type}/{id}/mentions` | Paginated mention evidence |
| `GET` | `…/{type}/{id}/connections` | Stylebook connections |
| `POST` | `…/{type}/semantic-search` | Natural-language mention search |

**Works:** return **501** or omit routes until `work` entity HTTP is implemented; document in the capability matrix.

---

## Custom records

Custom Extract output (`substrate_custom_record`) is part of the public API.

### Response shape

- `id`, `article_id`, `record_type`, `record_index`
- `fields` — parsed from `fields_json`
- `mentions` — parsed from `mentions_json` (evidence spans; no full article body)
- `field_schema` — from `field_schema_json` (so consumers can interpret historical rows)
- Optional `confidence`

### Routes

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `…/custom-records/search` | Filter by `record_type`, field values, `article_id`, date, keyword |
| `GET` | `…/articles/{article_id}/custom-records` | All records for one article |
| `GET` | `…/custom-records/{record_type}/{record_index}` | Single record (composite key within article) |

Field-value search semantics (equals vs contains) should be documented per field type in the reference; v1 can start with equality on string fields and exact `record_type`.

---

## Geography (cross-cutting)

Geography routes combine substrate geometry and Stylebook canonicals:

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `…/geo/location-types` | Distinct location types in project |
| `GET` | `…/geo/locations/search` | Search canonical/substrate locations by type + keyword |
| `GET` | `…/geo/locations/{id}/mentions` | Mentions linked to a location (with optional article meta filters) |

Article and entity list routes may accept optional **`location_id`** or **`bbox`** parameters where joins are defined in the query layer.

---

## Run trigger (exception to read-only)

Automation may **start an Agate run** without using session-based Agate API routes.

### Principles

- **Opt-in graphs:** only graphs explicitly marked **`public_run_enabled`** (new graph or project flag — exact storage TBD in Phase 1) may be triggered via the public API.
- **Input injection:** request body supplies parameters mapped to **ingress nodes** (TextInput, JSONInput, or a documented subset of S3Input batch parameters).
- **Same worker path** as `POST /runs` on Agate API (enqueue Celery; no duplicate execution engine).
- **Poll-only follow-up** on public API — no cancel, rerun, or review overlay.

### Routes

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `…/runs` | Start a run |
| `GET` | `…/runs/{run_id}` | Run status + minimal item summary |

**POST body (conceptual):**

```json
{
  "graph_id": "uuid-or-slug",
  "inputs": {
    "<ingress_node_id_or_alias>": { "text": "…" }
  }
}
```

Exact ingress mapping rules (node id vs stable alias, JSONInput shape) are specified during Phase 1 implementation. Public run responses omit internal cost breakdowns unless needed for billing integrations.

---

## Documentation for an external docs site

Maintain two artifacts in-repo (paths may shift; keep content in sync with code):

1. **OpenAPI** — FastAPI schema for `/public/v1` only (tagged `public-*`). Export via `GET /openapi.json` filtered or a dedicated export script.
2. **`docs/public-api/reference/`** — agent-ready markdown tree:
   - `README.md` — taxonomy, auth, pagination, error model
   - **`endpoints.md`** — **running list** of shipped routes (module path, parameters, responses, errors); update on every new endpoint
   - `capability-matrix.md` — which query modes exist per type and phase
   - `articles.md`, `locations.md`, `people.md`, … — route pages with parameters and example JSON
   - `runs.md` — run trigger contract

Another repo’s docs agent should be able to ingest **`reference/` + OpenAPI** without reading Stylebook or Agate internal route docs.

---

## Relationship to existing services

| Concern | Owner today | Public API approach |
|---------|-----------|---------------------|
| Article substrate | Worker / DBOutput | Read via core-api query layer |
| Stylebook canonicals | stylebook-api (editorial) | Read via core-api; writes stay internal |
| Semantic mention search | stylebook-api (POST, session) | Re-home read logic to shared layer; expose on public router |
| Run execution | agate-api `POST /runs` | Public POST delegates to shared enqueue helper |
| Project API keys | core-api credentials | Same keys for public consumers |

Internal Stylebook and Agate routes **do not move** in v1; public API **adds** a new surface rather than renaming editorial paths.

---

## Implementation plan

Work on branch **`feat/api-surface`** (or child branches per phase). Update this doc when routes ship or contracts change.

### Phase 0 — Design lock ✅

- [x] Organizing doc (this file)
- [ ] Review and sign off on URL layout, run-trigger rules, and capability matrix

### Phase 1 — Foundation

**Goal:** Empty but real public surface with auth, project scope, and doc export.

- [x] Add `core_api/routers/public/` package mounted at **`/public/v1`**
- [x] Project API key dependency (reuse `backfield_auth.gate` project key path)
- [x] Shared helpers: pagination envelope, project + stylebook resolution, OpenAPI tags
- [x] `GET /public/v1/projects/{project_slug}` — minimal project metadata (name, slug)
- [x] Running endpoint registry: **`docs/public-api/reference/endpoints.md`**
- [ ] Decide storage for **`public_run_enabled`** on graphs
- [x] Scaffold `docs/public-api/reference/README.md` and `capability-matrix.md`
- [x] Tests: auth, wrong project, 404 semantics

**Validation:** `make lint`, `make test`

### Phase 2 — Articles (tracer bullet)

**Goal:** Prove substrate queries and documentation shape.

- [x] `GET …/articles/search` — keyword, meta filters, date range
- [x] `GET …/articles/{article_id}` — detail without full body; optional preview
- [x] Registry entries in **`docs/public-api/reference/endpoints.md`**
- [x] Indexes: existing `substrate_article` / `substrate_article_meta` indexes cover v1 filters

**Validation:** `make lint`, `make test`, targeted integration tests

### Phase 2b — Article hub slices

**Goal:** Rich article context via sub-routes (not combinatorial `include` on detail).

- [x] `include=counts` on `GET …/articles/{article_id}`
- [x] `GET …/articles/{article_id}/mentions` — paginated; optional `entity_type`
- [x] `GET …/articles/{article_id}/locations` — geography / map-oriented shape
- [x] `GET …/articles/{article_id}/images`
- [x] Registry entries in **`endpoints.md`** for each shipped sub-route
- [x] Shared mention/location serializers in `backfield_entities.public.*`

**Validation:** `make lint`, `make test`

### Phase 3 — Custom records

**Goal:** Expose Custom Extract persistence publicly.

- `GET …/custom-records/search`
- `GET …/articles/{article_id}/custom-records`
- Reference page; field-type search semantics documented

**Validation:** `make lint`, `make test`

### Phase 4 — Canonical types (keyword + entity)

**Goal:** Consistent per-type search and detail.

Order by maturity:

1. **Locations** — search, detail, mentions, connections
2. **People** — same spine
3. **Organizations** — same spine
4. **Works** — stub or skip until entity type ships

Extract shared “canonical query” module in `backfield-entities` to avoid copy-paste across types.

**Validation:** `make lint`, `make test`

### Phase 5 — Semantic search

**Goal:** Public natural-language mention search.

- `POST …/{type}/semantic-search` for people and locations (organizations when embeddings exist)
- Reuse embedding model resolution from existing semantic indexing config
- **503** when embedding model missing

**Validation:** `make lint`, `make test`; optional stack test when embeddings configured

### Phase 6 — Geography

**Goal:** Cross-cutting geo queries and location-scoped filters on articles/mentions.

- `GET …/geo/location-types`
- `GET …/geo/locations/search`
- Optional bbox / `location_id` filters on article and mention routes

**Validation:** `make lint`, `make test`

### Phase 7 — Run trigger

**Goal:** Controlled automation entrypoint.

- Shared enqueue helper callable from agate-api and core-api public router
- `POST …/runs`, `GET …/runs/{run_id}` (minimal public run shape)
- Graph allowlist (`public_run_enabled`)
- Document ingress `inputs` mapping
- Reference page `runs.md`

**Validation:** `make lint`, `make test`, `make smoke` when run path touches worker enqueue

### Phase 8 — Docs handoff

**Goal:** External docs repo can generate the site.

- Export script for public OpenAPI subset
- Complete `docs/public-api/reference/` route pages
- Capability matrix reflects shipped phases
- Short “integration guide” (auth, rate limits TBD, pagination worked example)

---

## Capability matrix (target)

Update as phases complete. **Shipped** / **Planned** / **N/A**.

| Resource | Keyword | Entity detail | Mentions | Connections | Semantic | Geo filters |
|----------|---------|---------------|----------|-------------|----------|-------------|
| Articles (core) | ✅ | ✅ | — | — | — | — |
| Articles (hub) | — | — | ✅ | — | — | ✅ |
| Article images | — | ✅ | — | — | — | — |
| Custom records | Planned | Planned | — | — | — | — |
| Locations | Planned | Planned | Planned | Planned | Planned | Planned |
| People | Planned | Planned | Planned | Planned | Planned | Partial |
| Organizations | Planned | Planned | Planned | Planned | Planned | Partial |
| Works | N/A | N/A | N/A | N/A | N/A | N/A |
| Runs (trigger) | — | Planned | — | — | — | — |

---

## Open decisions (resolve in Phase 1)

1. **Graph public flag:** column on `agate_graph` vs project-level allowlist table.
2. **Ingress mapping:** node React Flow id vs declared stable alias in graph metadata.
3. **Article preview:** max characters and whether to index preview for search.
4. **Rate limiting:** defer to gateway vs middleware in core-api.
5. **Custom record search:** which field types support substring vs exact match in v1.

**Resolved (Phase 2):** article preview uses **280 characters** max (`PUBLIC_ARTICLE_PREVIEW_MAX_LEN` in `backfield_entities.public.articles`).

**Resolved (article hub):** use **lean detail + paginated sub-routes** (`/mentions`, `/locations`, `/custom-records`, `/images`); optional `include=counts` on detail only; optional `/bundle` later—not combinatorial `include` for heavy slices.
