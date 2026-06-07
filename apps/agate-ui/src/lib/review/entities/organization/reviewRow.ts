/** Review merged-organizations row metadata from processed item GET responses. */

export function getMergedRowAnchor(row: Record<string, unknown>): string {
  const anchor = row.anchor
  return typeof anchor === 'string' ? anchor : ''
}

export function getMergedRowPersistedOrganizationId(row: Record<string, unknown>): number | null {
  const raw = row.persisted_organization_id
  if (typeof raw === 'number' && Number.isFinite(raw) && raw > 0) {
    return Math.trunc(raw)
  }
  if (typeof raw === 'string' && raw.trim()) {
    const n = Number(raw)
    if (Number.isFinite(n) && n > 0) return Math.trunc(n)
  }
  return null
}

export function getMergedRowStylebookOrganizationCanonicalId(
  row: Record<string, unknown>,
): string | null {
  const raw = row.stylebook_organization_canonical_id
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

export function getMergedRowStylebookSlug(row: Record<string, unknown>): string | null {
  const raw = row.stylebook_slug
  if (typeof raw === 'string' && raw.trim()) {
    return raw.trim()
  }
  return null
}

export function resolveStylebookSlugForLinkedRow(
  row: Record<string, unknown>,
  workspaceStylebookSlug: string | null | undefined,
): string | null {
  return getMergedRowStylebookSlug(row) ?? (workspaceStylebookSlug?.trim() || null)
}

export function isMergedRowLinkedToStylebook(row: Record<string, unknown>): boolean {
  return (
    getMergedRowStylebookOrganizationCanonicalId(row) !== null &&
    getMergedRowStylebookLink(row) !== null
  )
}

export function newUserOrganizationId(): string {
  const u =
    typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `user_organization:${u}`
}

export function isReviewOnlyMergedOrganizationRow(row: Record<string, unknown>): boolean {
  return getMergedRowPersistedOrganizationId(row) === null
}

export function readOrganizationFromRow(row: Record<string, unknown>): Record<string, unknown> {
  const organization = row.organization
  if (organization && typeof organization === 'object' && !Array.isArray(organization)) {
    return organization as Record<string, unknown>
  }
  return {}
}

export function organizationDisplayName(row: Record<string, unknown>): string {
  const organization = readOrganizationFromRow(row)
  const name = organization.name
  if (typeof name === 'string' && name.trim()) {
    return name.trim()
  }
  return getMergedRowAnchor(row) || 'Organization'
}
