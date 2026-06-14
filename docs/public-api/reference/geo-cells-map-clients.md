# Geo-cells map client guide

Guidance for frontends building hex coverage maps on `GET /public/v1/projects/{project_slug}/articles/geo-cells`.

Design reference: [`endpoints.md`](endpoints.md) (route contract) · [`../../PUBLIC_API.md`](../../PUBLIC_API.md) (taxonomy).

## Core model (unchanged)

Each request returns **one display resolution `R`** and a flat list of hex cells with **distinct-article counts**.

| Rule | Behavior |
|------|----------|
| Count unit | One article counts once per cell, even with multiple place mentions in that cell |
| Rollup | Locations with native `h3_resolution >= R` roll up to parent cell at `R` via `h3_cell_to_parent` |
| Size gate | Locations with native `h3_resolution < R` are **excluded** — not subdivided, not included at native size |
| Blow-up guard | 5,000-cell ceiling enforced by **auto-coarsen** (lowers `R`), not by rejecting the request |

The size gate is the smart-by-default mechanism for zoom-aware coverage. A general "Chicago" mention (native res ~5) is excluded at block zoom (`R=9+`) and reappears only when the display resolution is coarse enough that a city-sized hex is appropriate. **No `location_type` filters or per-zoom configuration are required.**

## What changed (v2 behavior)

### 1. Resolution selection

**Before:** `resolution` override was clamped to a bbox-derived maximum. A city-wide viewport forced coarse `R` even when the client passed a fine resolution.

**Now:**

- Omit `resolution` → server derives `R` from bbox viewport size (`derived_resolution` in the response).
- Pass `resolution` → honored as the **starting** resolution. The bbox no longer clamps it down.
- If the result exceeds 5,000 cells → server decrements `R` until under the cap (`coarsened: true`).

**Client guidance:** Map the Leaflet zoom level to an H3 resolution table and pass it as `resolution` on every pan/zoom. The bbox already encodes the viewport; a separate `zoom` param is unnecessary.

Example resolution hints (tune per product):

| Leaflet zoom (approx) | Suggested `resolution` |
|-----------------------|------------------------|
| 8–9 (metro) | 5–6 |
| 10–11 (city) | 6–7 |
| 12–13 (neighborhood) | 8–9 |
| 14+ (block) | 10–11 |

### 2. Response metadata

```json
{
  "resolution": 7,
  "derived_resolution": 5,
  "requested_resolution": 8,
  "bbox_extent_km": 12.4,
  "coarsened": true,
  "cells": [
    { "h3_cell": "872664c47ffffff", "article_count": 12 }
  ]
}
```

| Field | Use in UI |
|-------|-----------|
| `resolution` | Draw all cells at this H3 resolution |
| `derived_resolution` | What the server would pick without an override — useful for debugging |
| `requested_resolution` | What you asked for (`null` when omitted) |
| `bbox_extent_km` | Viewport size context |
| `coarsened` | Show a status hint when `true` ("Showing coarser hexes due to data density") |

### 3. Auto-coarsen replaces 400

**Before:** >5,000 cells → `400` error; client had to retry with a coarser resolution.

**Now:** Server lowers `R` automatically. Check `coarsened` and `resolution` in the response. Reserve client retry logic for network errors only.

## What we are **not** doing

These were considered and rejected because they conflict with the size-gate model or add complexity without proportional benefit:

| Proposal | Why not |
|----------|---------|
| Include coarse locations at fine zoom (mixed-resolution cells) | Would put "Chicago" back into block-level views — the pollution problem the size gate solves |
| Per-cell `h3_resolution` in the response | Implies mixed-resolution rendering; breaks single-`R` distinct-count semantics |
| `zoom` query param separate from bbox | Redundant inputs that can disagree; bbox + `resolution` is sufficient |
| Mention-level H3 indexing | Mentions have no geometry today; coarseness reflects extracted location footprint, not an indexing bug |
| `include=boundaries` | Low priority; client-side `h3-js` is fine for boundary rendering |

## Recommended client integration

1. **On map move/zoom:** compute bbox from `map.getBounds()`, map zoom → `resolution`, `GET …/geo-cells?bbox=…&resolution=…`.
2. **Render:** draw each returned cell at `response.resolution` using `h3_cell` IDs. Do not subdivide or merge on the client.
3. **Status bar:** when `coarsened`, show that the effective resolution is lower than requested. When `requested_resolution` differs from `resolution` only because of coarsen, explain density — not bbox clamping.
4. **Expect sparse fine zoom:** block-level cells appear only where extracted locations are point-scale (native res 9–11). City-name mentions stay coarse and correctly disappear when zoomed in.

## Drill-down

When a user clicks a hex:

1. Call `GET …/articles/geo-cells/{h3_cell}` with the cell ID from the coverage response.
2. Forward the **same filters** (`nature`, `location_type`, metadata, dates) that were active on the coverage request.
3. Use `pagination.total` to cross-check against the cell's `article_count` from `geo-cells`.
4. Render the article list from `items[]`; show `matching_locations` as the places that contributed to this cell.

Do not convert the hex to a bbox and call `geo-search` — that uses different matching (PostGIS geometry, no size gate) and counts will not align.

## Debugging checklist

| Symptom | Likely cause |
|---------|--------------|
| Only a few huge hexes at city zoom | Data is mostly city/county-level mentions — expected; not an API bug |
| Empty cells at block zoom | Size gate working: no locations with `h3_resolution >= R` in bbox |
| `coarsened: true` at fine zoom | Dense point data in viewport; server lowered `R` for the 5,000-cell cap |
| Count drops when zooming in | Coarse mentions excluded by size gate — expected |
| Same article, count 1 at all zooms | Distinct-article semantics — expected |

## Open questions (future, not v1)

- `clip_to_bbox=true` — count only mentions whose representative point falls inside the bbox (reduces edge bleed from coarse hexes touching the viewport edge).
- Finer default resolution table tuning from real project data.
