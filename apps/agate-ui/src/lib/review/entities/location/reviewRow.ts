/**
 * Review merged-location row metadata from ``GET /runs/{id}/items/{item_id}``.
 * See ``docs/api/processed-item-review.md`` → *Entity review domains*.
 */

import type { ArticleContext } from '@/lib/api'
import { extractGeometryFromPlace } from './placeGeometry'

const ARTICLE_ID_INPUT_KEYS = ['input_article_id', 'article_id', 'substrate_article_id'] as const

const ARTICLE_ID_OUTPUT_KEYS = ['stylebook_output', 'geocode_agent', 'place_extract'] as const

function parseArticleIdFromPersistedOutput(
  output: Record<string, unknown> | undefined,
): number | null {
  if (!output || typeof output !== 'object') return null
  for (const key of ARTICLE_ID_OUTPUT_KEYS) {
    const block = output[key]
    if (!block || typeof block !== 'object') continue
    const hit = parsePositiveArticleId((block as Record<string, unknown>).article_id)
    if (hit !== null) return hit
  }
  return null
}

function parsePositiveArticleId(raw: unknown): number | null {
  if (typeof raw === 'number' && Number.isFinite(raw) && raw > 0) {
    return Math.trunc(raw)
  }
  if (typeof raw === 'string' && raw.trim()) {
    const n = Number(raw)
    if (Number.isFinite(n) && n > 0) return Math.trunc(n)
  }
  return null
}

/** Article id for story-scoped Stylebook calls (matches API ``processed_item.content.article_context``). */
export function resolveProcessedItemArticleId(
  articleContext: ArticleContext | undefined,
  itemInput: Record<string, unknown> | undefined,
  itemOutput?: Record<string, unknown> | undefined,
): number | null {
  const fromContext = parsePositiveArticleId(articleContext?.article_id)
  if (fromContext !== null) return fromContext
  if (!itemInput || typeof itemInput !== 'object') {
    return parseArticleIdFromPersistedOutput(itemOutput)
  }
  for (const key of ARTICLE_ID_INPUT_KEYS) {
    const hit = parsePositiveArticleId(itemInput[key])
    if (hit !== null) return hit
  }
  return parseArticleIdFromPersistedOutput(itemOutput)
}

export interface MergedRowStylebookLink {
  label: string
  has_geometry: boolean
  geometry_differs: boolean
}

export function getMergedRowPersistedLocationId(row: Record<string, unknown>): number | null {
  const raw = row.persisted_location_id
  if (typeof raw === 'number' && Number.isFinite(raw) && raw > 0) {
    return Math.trunc(raw)
  }
  if (typeof raw === 'string' && raw.trim()) {
    const n = Number(raw)
    if (Number.isFinite(n) && n > 0) return Math.trunc(n)
  }
  return null
}

export function getMergedRowStylebookCanonicalId(row: Record<string, unknown>): string | null {
  const raw = row.stylebook_location_canonical_id
  if (typeof raw === 'string' && raw.trim()) {
    return raw.trim()
  }
  return null
}

/** Stylebook that owns the linked canonical (preferred over project workspace slug). */
export function getMergedRowStylebookSlug(row: Record<string, unknown>): string | null {
  const raw = row.stylebook_slug
  if (typeof raw === 'string' && raw.trim()) {
    return raw.trim()
  }
  return null
}

/** Slug for deep links to a linked canonical; row slug wins over workspace default. */
export function resolveStylebookSlugForLinkedRow(
  row: Record<string, unknown>,
  workspaceStylebookSlug: string | null | undefined,
): string | null {
  return getMergedRowStylebookSlug(row) ?? (workspaceStylebookSlug?.trim() || null)
}

export function getMergedRowStylebookLink(row: Record<string, unknown>): MergedRowStylebookLink | null {
  const link = row.stylebook_link
  if (!link || typeof link !== 'object' || Array.isArray(link)) {
    return null
  }
  const o = link as Record<string, unknown>
  const label = typeof o.label === 'string' ? o.label.trim() : ''
  if (!label) return null
  return {
    label,
    has_geometry: o.has_geometry === true,
    geometry_differs: o.geometry_differs === true,
  }
}

export function isMergedRowLinkedToStylebook(row: Record<string, unknown>): boolean {
  return getMergedRowStylebookCanonicalId(row) !== null && getMergedRowStylebookLink(row) !== null
}

/** True when Adopt for Stylebook should appear (linked, saved geometry, differs from canonical). */
export function shouldShowAdoptForStylebook(row: Record<string, unknown>): boolean {
  if (!isMergedRowLinkedToStylebook(row)) {
    return false
  }
  const link = getMergedRowStylebookLink(row)
  if (!link?.geometry_differs) {
    return false
  }
  const loc = row.location
  return extractGeometryFromPlace(
    loc && typeof loc === 'object' && !Array.isArray(loc) ? (loc as Record<string, unknown>) : null,
  ) !== null
}

export function isReviewOnlyMergedRow(row: Record<string, unknown>): boolean {
  return getMergedRowPersistedLocationId(row) === null
}
