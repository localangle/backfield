/** Stylebook UI segments catalogs under `/stylebook/<slug>/…`. */

import { STYLEBOOK_URL_QUERY_KEY } from "@/lib/stylebook-api/client"

export function stylebookCatalogBasePath(stylebookSlug: string): string {
  const s = stylebookSlug.trim()
  if (!s) return "/stylebook/default"
  return `/stylebook/${encodeURIComponent(s)}`
}

/** Strip `/stylebook/<slug>` from pathname if present. */
export function parseStylebookSlugFromPath(pathname: string): string | null {
  const m = pathname.match(/^\/stylebook\/([^/]+)\/?/)
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
