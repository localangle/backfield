/** Review merged-people row metadata from processed item GET responses. */

export function getMergedRowAnchor(row: Record<string, unknown>): string {
  const anchor = row.anchor
  return typeof anchor === 'string' ? anchor : ''
}

export function getMergedRowPersistedPersonId(row: Record<string, unknown>): number | null {
  const raw = row.persisted_person_id
  if (typeof raw === 'number' && Number.isFinite(raw) && raw > 0) {
    return Math.trunc(raw)
  }
  if (typeof raw === 'string' && raw.trim()) {
    const n = Number(raw)
    if (Number.isFinite(n) && n > 0) return Math.trunc(n)
  }
  return null
}

export function getMergedRowStylebookPersonCanonicalId(row: Record<string, unknown>): string | null {
  const raw = row.stylebook_person_canonical_id
  if (typeof raw === 'string' && raw.trim()) {
    return raw.trim()
  }
  return null
}

export function getMergedRowStylebookLink(row: Record<string, unknown>): { label: string } | null {
  const link = row.stylebook_link
  if (!link || typeof link !== 'object') return null
  const label = (link as { label?: unknown }).label
  if (typeof label === 'string' && label.trim()) {
    return { label: label.trim() }
  }
  return null
}

export function getMergedRowCanonicalLinkStatus(row: Record<string, unknown>): string | null {
  const raw = row.canonical_link_status
  if (typeof raw === 'string' && raw.trim()) {
    return raw.trim()
  }
  return null
}

export function isMergedRowLinkedToStylebook(row: Record<string, unknown>): boolean {
  return getMergedRowStylebookPersonCanonicalId(row) !== null
}

export function isReviewOnlyMergedPersonRow(row: Record<string, unknown>): boolean {
  return getMergedRowPersistedPersonId(row) === null
}

export function readPersonFromRow(row: Record<string, unknown>): Record<string, unknown> {
  const person = row.person
  if (person && typeof person === 'object' && !Array.isArray(person)) {
    return person as Record<string, unknown>
  }
  return {}
}

export function personDisplayName(row: Record<string, unknown>): string {
  const person = readPersonFromRow(row)
  const name = person.name
  if (typeof name === 'string' && name.trim()) {
    return name.trim()
  }
  return getMergedRowAnchor(row) || 'Person'
}
