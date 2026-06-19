# Batch geo-cells query spec

Design reference for `POST /public/v1/projects/{project_slug}/articles/geo-cells/query`.

## Problem

Perspective refresh with geographic retrievers currently fans out to one `GET …/articles/geo-cells/{h3_cell}` call per selected cell (sequentially), multiplied by subject filters and pagination. A retriever with 20 cells and 2 subject variants can require hundreds of HTTP round-trips even though the client dedupes articles afterward.

Coverage maps already batch counts via `GET …/articles/geo-cells?bbox=…`. This endpoint batches **drill-down** (articles + matching locations).

## Endpoint

```
POST /public/v1/projects/{project_slug}/articles/geo-cells/query
```

Use POST so large `cells[]` arrays are not limited by URL length.

### Request body

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cells` | string[] | yes | H3 cell IDs at the shared display resolution (1–200 entries) |
| `resolution` | integer | yes | Display resolution shared by all cells (0–15) |
| `location_type` | string | no | Filter matching locations by substrate `location_type` |
| `nature` | string | no | Filter matching location mentions by editorial `nature` |
| `meta_type` | string | no | Include articles with this metadata type |
| `meta_category` | string | no | With `meta_type`, include this category |
| `exclude_meta_type` | string | no | Exclude articles with this metadata type |
| `exclude_meta_category` | string | no | With `exclude_meta_type`, exclude this category |
| `external_source` | string | no | Include articles from this external source (case-insensitive) |
| `pub_date_from` | string | no | ISO date `YYYY-MM-DD`, inclusive lower bound |
| `pub_date_to` | string | no | ISO date `YYYY-MM-DD`, inclusive upper bound |
| `limit` | integer | no | Page size (1–100, default 25) |
| `offset` | integer | no | Offset for pagination (default 0) |
| `include_preview` | boolean | no | Include truncated text preview per article (default false) |

Example:

```json
{
  "cells": ["872664c1affffff", "872664c1effffff"],
  "resolution": 7,
  "meta_type": "subject",
  "meta_category": "public_safety_crime",
  "pub_date_from": "2024-01-01",
  "include_preview": true,
  "limit": 100,
  "offset": 0
}
```

### Response `200`

Flat, deduplicated by article. Pagination is over the merged article set, ordered by `pub_date` descending (nulls last), then `id` descending — same as single-cell drill-down.

```json
{
  "resolution": 7,
  "items": [
    {
      "article": { "id": 1, "headline": "…", "metadata": [] },
      "matching_locations": [ { "mention_id": 10, "label": "City Hall" } ],
      "matched_cells": ["872664c1affffff", "872664c1effffff"]
    }
  ],
  "per_cell_totals": [
    { "h3_cell": "872664c1affffff", "article_count": 12 },
    { "h3_cell": "872664c1effffff", "article_count": 8 }
  ],
  "pagination": { "limit": 100, "offset": 0, "total": 15 }
}
```

- **`matched_cells`**: requested hexes the article matched through (provenance for multi-cell selections).
- **`per_cell_totals`**: distinct-article counts per requested cell after filters; use to cross-check coverage map counts.

### Semantics

Same H3 rollup + size gate as `GET …/articles/geo-cells/{h3_cell}`:

- `R = resolution` from the request body
- Include a location mention when `h3_resolution >= R` and it rolls up to one of the requested cells
- Coarse-native locations are excluded at fine cells

**Equivalence:** one cell in `cells` with matching `resolution` must return the same merged article set as the single-cell GET (modulo `matched_cells`).

### Errors

| Status | When |
|--------|------|
| `400` | Empty `cells`, invalid cell ID, resolution mismatch, >200 cells, invalid dates |
| `401` | Missing or invalid API key |
| `403` | API key not valid for this project |
| `404` | Unknown `project_slug` |

## Client usage (Proof)

| Scenario | Today | With batch |
|----------|-------|------------|
| 20 cells × 2 subjects | ~40+ GET requests | 2+ POST pages |
| Perspective refresh | Sequential per-cell fan-out | One POST per page / subject variant |

Migration: call batch first; fall back to per-cell GET on `404` for older local APIs.

## v1 scope

Shipped in v1:

- Flat merged `items[]` with `matched_cells`
- Global pagination over deduplicated articles
- `per_cell_totals`
- `external_source` filter on batch body

Deferred:

- `meta_categories` OR (multiple categories in one request)
- Grouped-by-cell response shape
- `external_source` on single-cell GET (batch-only for now)

## Open questions

- Max cells cap: **200** in v1
- Parallel per-cell fan-out as interim client optimization (does not reduce DB load)
- Two-phase ID-only batch response (not v1)
