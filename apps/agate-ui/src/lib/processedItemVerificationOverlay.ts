/**
 * Draft overlay state for processed-item verification (Issue 4).
 * Aligns with ``docs/API.md`` → processed item location overlay (v1).
 */

export function emptyOverlay(): Record<string, unknown> {
  return {
    locations: {
      by_anchor: {} as Record<string, unknown>,
      user_added: [] as unknown[],
    },
  }
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function deepSortKeys(value: unknown): unknown {
  if (value === null || typeof value !== 'object') {
    return value
  }
  if (Array.isArray(value)) {
    return value.map(deepSortKeys)
  }
  const o = value as Record<string, unknown>
  const out: Record<string, unknown> = {}
  for (const k of Object.keys(o).sort()) {
    out[k] = deepSortKeys(o[k])
  }
  return out
}

export function overlaysStructurallyEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(deepSortKeys(a)) === JSON.stringify(deepSortKeys(b))
}

/**
 * Normalize overlay JSON so ``locations.by_anchor`` and ``locations.user_added`` exist.
 */
export function normalizeOverlay(
  overlay: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  const base = emptyOverlay()
  if (!overlay || typeof overlay !== 'object') {
    return cloneJson(base)
  }
  const out = cloneJson(overlay) as Record<string, unknown>
  const locRaw = out.locations
  if (!locRaw || typeof locRaw !== 'object' || Array.isArray(locRaw)) {
    out.locations = cloneJson(base.locations)
    return out
  }
  const loc = locRaw as Record<string, unknown>
  const by = loc.by_anchor
  loc.by_anchor =
    typeof by === 'object' && by !== null && !Array.isArray(by)
      ? { ...(by as Record<string, unknown>) }
      : {}
  const ua = loc.user_added
  loc.user_added = Array.isArray(ua) ? [...ua] : []
  out.locations = loc
  return out
}

function ensureLocations(draft: Record<string, unknown>): Record<string, unknown> {
  if (!draft.locations || typeof draft.locations !== 'object' || Array.isArray(draft.locations)) {
    draft.locations = cloneJson(emptyOverlay().locations) as Record<string, unknown>
  }
  const loc = draft.locations as Record<string, unknown>
  if (!loc.by_anchor || typeof loc.by_anchor !== 'object' || Array.isArray(loc.by_anchor)) {
    loc.by_anchor = {}
  }
  if (!Array.isArray(loc.user_added)) {
    loc.user_added = []
  }
  return loc
}

/**
 * True when the merged place row is treated as linked to a catalog canonical and must stay read-only here.
 */
export function isLocationLinkedToStylebookCanonical(location: unknown): boolean {
  if (!location || typeof location !== 'object' || Array.isArray(location)) {
    return false
  }
  const loc = location as Record<string, unknown>
  const sid = loc.stylebook_location_canonical_id
  if (typeof sid === 'string' && sid.trim().length > 0) {
    return true
  }
  if (typeof sid === 'number' && !Number.isNaN(sid)) {
    return true
  }
  if (loc.canonical_link_status === 'linked') {
    return true
  }
  const geocode = loc.geocode
  if (geocode && typeof geocode === 'object' && !Array.isArray(geocode)) {
    const res = (geocode as Record<string, unknown>).result
    if (res && typeof res === 'object' && !Array.isArray(res)) {
      const cid = (res as Record<string, unknown>).canonical_id
      if (typeof cid === 'string' && cid.trim().length > 0) {
        return true
      }
    }
  }
  return false
}

/**
 * Catalog canonical id for opening Stylebook from a linked place row (UUID string when present).
 */
export function getStylebookCanonicalHandoffId(location: unknown): string | null {
  if (!location || typeof location !== 'object' || Array.isArray(location)) {
    return null
  }
  const loc = location as Record<string, unknown>
  const sid = loc.stylebook_location_canonical_id
  if (typeof sid === 'string' && sid.trim().length > 0) {
    return sid.trim()
  }
  if (typeof sid === 'number' && !Number.isNaN(sid)) {
    return String(Math.trunc(sid))
  }
  const geocode = loc.geocode
  if (geocode && typeof geocode === 'object' && !Array.isArray(geocode)) {
    const res = (geocode as Record<string, unknown>).result
    if (res && typeof res === 'object' && !Array.isArray(res)) {
      const cid = (res as Record<string, unknown>).canonical_id
      if (typeof cid === 'string' && cid.trim().length > 0) {
        return cid.trim()
      }
    }
  }
  return null
}

export function getMergedRowAnchor(row: Record<string, unknown>): string {
  const a = row.anchor
  return typeof a === 'string' ? a : ''
}

export function getLocationDescription(location: unknown): string {
  if (!location || typeof location !== 'object' || Array.isArray(location)) {
    return ''
  }
  const d = (location as Record<string, unknown>).description
  return typeof d === 'string' ? d : ''
}

/**
 * Shallow-merge a ``description`` patch into ``locations.by_anchor[anchor]`` on the draft overlay.
 */
export function applyDescriptionPatch(
  draft: Record<string, unknown>,
  anchor: string,
  description: string,
): void {
  const loc = ensureLocations(draft)
  const by = loc.by_anchor as Record<string, unknown>
  const cur = by[anchor]
  const patch: Record<string, unknown> =
    typeof cur === 'object' && cur !== null && !Array.isArray(cur)
      ? { ...(cur as Record<string, unknown>) }
      : {}
  patch.description = description
  by[anchor] = patch
}

export function isApiConflictError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false
  }
  return /\b409\b/.test(error.message)
}
