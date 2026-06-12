# Capability matrix

Tracks which **public** query modes are shipped. Update when routes land. Design reference: [`../../PUBLIC_API.md`](../../PUBLIC_API.md).

Legend: ✅ Shipped · 🚧 Planned · ➖ Not applicable · ❌ Not planned (v1)

## Articles

| Mode | Status | Notes |
|------|--------|-------|
| Keyword search | ✅ | `GET …/articles/search` |
| Detail | ✅ | No full body; optional preview |
| Mentions index | 🚧 | Optional v1 |
| Metadata filters | ✅ | `meta_type`, `meta_category`, date range |
| Geo filters | 🚧 | Phase 6 |

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
| Keyword search | 🚧 | |
| Detail | 🚧 | |
| Mentions | 🚧 | |
| Connections | 🚧 | |
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
