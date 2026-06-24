# Capability matrix

Tracks which **public** query modes are shipped. Update when routes land. Design reference: [`../../PUBLIC_API.md`](../../PUBLIC_API.md).

Legend: ✅ Shipped · 🚧 Planned · ➖ Not applicable · ❌ Not planned (v1)

## Articles

| Mode | Status | Notes |
|------|--------|-------|
| Keyword search | ✅ | `GET …/articles/search` |
| Search facets | ✅ | `GET …/articles/facets` (authors, sources, preset metadata categories) |
| Metadata types | ✅ | `GET …/articles/metadata/types` |
| Metadata values | ✅ | `GET …/articles/metadata/types/{meta_type}/values` |
| Article metadata | ✅ | `GET …/articles/{id}/metadata` |
| Semantic search | ✅ | `POST …/articles/semantic-search` (requires `substrate_article_embedding`; optional HyDE via `use_hyde`) |
| Geo search | ✅ | `GET …/articles/geo-search` (point+radius or bbox; location mentions) |
| Geo cells (hex coverage) | ✅ | `GET …/articles/geo-cells` (bbox; distinct-article counts per H3 cell) |
| Geo cell drill-down | ✅ | `GET …/articles/geo-cells/{h3_cell}` (articles + in-cell location mentions) |
| Batch geo cell drill-down | ✅ | `POST …/articles/geo-cells/query` (many cells; deduplicated articles + `matched_cells`) |
| Detail | ✅ | Preview always; optional `include=text` for full body; inline images (≤10); optional `include=counts` |
| Article counts (`include=counts`) | ✅ | Mention totals, distinct canonical totals, image/custom-record counts, `embedded` on search + detail |
| Mentions (hub) | ✅ | `GET …/articles/{id}/mentions`; `entity_type`, `nature`, `quote` filters |
| Locations (hub) | ✅ | `GET …/articles/{id}/locations` — map-oriented |
| Images (hub) | ✅ | `GET …/articles/{id}/images` |
| Metadata filters | ✅ | Legacy `meta_type` / exclude params plus repeatable `meta` clauses on keyword search, semantic search, geo search, geo cells (+ drill-down/batch), and mention search |
| Geo filters (search) | ✅ | `GET …/articles/geo-search` |
| Bundle (convenience) | ❌ | Not v1; optional later |

## Custom records

| Mode | Status | Notes |
|------|--------|-------|
| Search | 🚧 | By `record_type`, article, field values |
| By article | 🚧 | `GET …/articles/{id}/custom-records` |
| Detail | 🚧 | Composite key within article |

## Locations

| Mode | Status | Notes |
|------|--------|-------|
| Keyword search | ✅ | `GET …/locations` and `GET …/locations/search` |
| Geo search | ✅ | `GET …/locations/geo-search` (canonical geometry; point+radius or bbox) |
| Type facets | ✅ | `GET …/locations/types` |
| Detail | ✅ | UUID canonical id; includes geometry |
| Mentions | ✅ | `GET …/locations/{id}/mentions` |
| Articles | ✅ | `GET …/locations/{id}/articles` |
| Connections | ✅ | `GET …/locations/{id}/connections` |
| Semantic search | 🚧 | Phase 5 |

## People

| Mode | Status | Notes |
|------|--------|-------|
| Keyword search | ✅ | `GET …/people` and `GET …/people/search` |
| Type facets | ✅ | `GET …/people/types` |
| Detail | ✅ | UUID canonical id |
| Mentions | ✅ | `GET …/people/{id}/mentions` |
| Articles | ✅ | `GET …/people/{id}/articles` |
| Connections | ✅ | `GET …/people/{id}/connections` |
| Semantic search | 🚧 | Phase 5 |
| Geography | 🚧 | Via mention/article filters |

## Organizations

| Mode | Status | Notes |
|------|--------|-------|
| Keyword search | ✅ | `GET …/organizations` and `GET …/organizations/search` |
| Type facets | ✅ | `GET …/organizations/types` |
| Detail | ✅ | UUID canonical id |
| Mentions | ✅ | `GET …/organizations/{id}/mentions` |
| Articles | ✅ | `GET …/organizations/{id}/articles` |
| Connections | ✅ | `GET …/organizations/{id}/connections` |
| Semantic search | 🚧 | Phase 5 |
| Geography | 🚧 | Via mention/article filters |

## Mentions (project-wide)

| Mode | Status | Notes |
|------|--------|-------|
| Keyword search | ✅ | `GET …/mentions/search` — unified across entity types |
| Facets | ✅ | `GET …/mentions/facets` — entity types, natures, type values |
| Detail | ✅ | `GET …/mentions/{entity_type}/{mention_id}` — all occurrences |
| Article/metadata filters | ✅ | On search: author, source, section, legacy meta include/exclude, repeatable `meta` clauses, date range |
| Semantic search | 🚧 | Phase 5 (per-type `…/{type}/semantic-search`) |
| Geo search | 🚧 | Phase 6 |

## Works

| Mode | Status | Notes |
|------|--------|-------|
| All modes | ➖ | Entity type not implemented |

## Runs (automation)

| Mode | Status | Notes |
|------|--------|-------|
| Trigger | 🚧 | `POST …/runs`; graph allowlist |
| Poll status | 🚧 | `GET …/runs/{id}`; minimal shape |
| Cancel / rerun / review | ❌ | Editorial Agate API only |
