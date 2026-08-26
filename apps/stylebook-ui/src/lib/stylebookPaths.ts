/** Stylebook UI segments catalogs under `/stylebook/<slug>/…`. */

import { STYLEBOOK_URL_QUERY_KEY } from "@/lib/stylebook-api/client"
import type { EntityType } from "@/lib/entityTypes"

export function stylebookCatalogBasePath(stylebookSlug: string): string {
  const s = stylebookSlug.trim()
  if (!s) return "/stylebook/default"
  return `/stylebook/${encodeURIComponent(s)}`
}

/** Absolute URL for an entity's catalog detail page, scoped to the current catalog. */
export function entityDetailUrl(
  entityType: EntityType,
  entityId: string | number,
  catalogBasePath: string,
  scopeSuffix: string,
): string {
  const base = window.location.origin
  const prefix = `${base}${catalogBasePath}`
  if (entityType === "person") {
    return `${prefix}/people/canonical/${entityId}${scopeSuffix}`
  }
  if (entityType === "organization") {
    return `${prefix}/organizations/canonical/${entityId}${scopeSuffix}`
  }
  if (entityType === "work") {
    return `${prefix}/works/canonical/${entityId}${scopeSuffix}`
  }
  return `${prefix}/locations/canonical/${entityId}${scopeSuffix}`
}

/** Strip `/stylebook/<slug>` from pathname if present. */
export function parseStylebookSlugFromPath(pathname: string): string | null {
  const m = pathname.match(/^(?:\/org\/[^/]+)?\/stylebook\/([^/]+)\/?/)
  return m ? decodeURIComponent(m[1]) : null
}

/** Legacy query-only URLs (`/?stylebook=`) → slug string or null. */
export function parseLegacyStylebookQuery(search: string): string | null {
  const trimmed = search.startsWith("?") ? search.slice(1) : search
  const q = new URLSearchParams(trimmed)
  const raw = q.get(STYLEBOOK_URL_QUERY_KEY)
  const s = (raw ?? "").trim()
  return s.length ? s : null
}

export function stripLegacyStylebookFromSearch(search: string): string {
  const trimmed = search.startsWith("?") ? search.slice(1) : search
  const q = new URLSearchParams(trimmed)
  q.delete(STYLEBOOK_URL_QUERY_KEY)
  const s = q.toString()
  return s ? `?${s}` : ""
}
