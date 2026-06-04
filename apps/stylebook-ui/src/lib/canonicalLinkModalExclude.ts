/** Canonical ids that must not appear in link/move picker lists. */
export function buildCanonicalLinkExcludeIds(
  linkedCanonicalId: string | null,
  excludeCanonicalId?: string | null,
): Set<string> {
  const ids = new Set<string>()
  for (const raw of [linkedCanonicalId, excludeCanonicalId]) {
    const id = (raw ?? "").trim()
    if (id) ids.add(id)
  }
  return ids
}

export function isExcludedCanonicalLinkTarget(
  canonicalId: string,
  excludeIds: ReadonlySet<string>,
): boolean {
  return excludeIds.has(String(canonicalId).trim())
}
