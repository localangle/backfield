# Capability matrix

Tracks which **public** query modes are shipped. Update when routes land. Design reference: [`../../PUBLIC_API.md`](../../PUBLIC_API.md).

Legend: ✅ Shipped · 🚧 Planned · ➖ Not applicable · ❌ Not planned (v1)

## Articles

| Mode | Status | Notes |
|------|--------|-------|
| Keyword search | ✅ | `GET …/articles/search` |
| Semantic search | ✅ | `POST …/articles/semantic-search` (requires `substrate_article_embedding`) |
| Geo search | ✅ | `GET …/articles/geo-search` (point+radius or bbox; location mentions) |
| Detail | ✅ | No full body; optional preview |
| Detail counts embed | ✅ | `include=counts` on detail |
| Mentions (hub) | ✅ | `GET …/articles/{id}/mentions`; `entity_type` filter |
| Locations (hub) | ✅ | `GET …/articles/{id}/locations` — map-oriented |
| Images (hub) | ✅ | `GET …/articles/{id}/images` |
| Metadata filters | ✅ | On search: include/exclude `meta_type` + category, date range |
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
| Keyword search | 🚧 | |
| Detail | 🚧 | UUID canonical id |
| Mentions | 🚧 | |
| Connections | 🚧 | |
| Semantic search | 🚧 | Phase 5 |
| Geography | 🚧 | Richest geo surface |

## People

| Mode | Status | Notes |
|------|--------|-------|
| Keyword search | ✅ | `GET …/people` and `GET …/people/search` |
| Type facets | ✅ | `GET …/people/types` |
| Detail | ✅ | UUID canonical id |
| Mentions | ✅ | `GET …/people/{id}/mentions` |
| Connections | ✅ | `GET …/people/{id}/connections` |
| Semantic search | 🚧 | Phase 5 |
| Geography | 🚧 | Via mention/article filters |

## Organizations

| Mode | Status | Notes |
|------|--------|-------|
| Keyword search | 🚧 | |
| Detail | 🚧 | |
| Mentions | 🚧 | |
| Connections | 🚧 | |
| Semantic search | 🚧 | When embeddings exist |
| Geography | 🚧 | Via mention/article filters |

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
