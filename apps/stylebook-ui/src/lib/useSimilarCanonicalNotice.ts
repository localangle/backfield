import { useCallback, useEffect, useMemo, useState } from "react"
import {
  listCanonicalLocations,
  listCanonicalOrganizations,
  listCanonicalPeople,
} from "@/lib/api"
import type { CleanupEntityType } from "@/lib/cleanupChecks"
import { duplicateSearchQuery, isMaterialDuplicateLabel } from "@/lib/similarCanonicalMatch"

export interface SimilarCanonicalMatch {
  id: string
  label: string
}

const SEARCH_LIMIT = 25

function ignoreStorageKey(canonicalId: string): string {
  return `stylebook.similarNoticeIgnored.${canonicalId}`
}

function readIgnoredIds(canonicalId: string): string[] {
  try {
    const raw = window.localStorage.getItem(ignoreStorageKey(canonicalId))
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : []
  } catch {
    return []
  }
}

function writeIgnoredIds(canonicalId: string, ids: string[]): void {
  try {
    window.localStorage.setItem(ignoreStorageKey(canonicalId), JSON.stringify(ids))
  } catch {
    // Ignore storage failures (private mode, quota); the notice just reappears.
  }
}

async function searchCanonicalsByType(
  entityType: CleanupEntityType,
  stylebookSlug: string,
  q: string,
  project?: string,
): Promise<SimilarCanonicalMatch[]> {
  if (entityType === "person") {
    const res = await listCanonicalPeople(stylebookSlug, q, SEARCH_LIMIT, 0, undefined, project)
    return res.canonicals.map((c) => ({ id: c.id, label: c.label }))
  }
  if (entityType === "organization") {
    const res = await listCanonicalOrganizations(
      stylebookSlug,
      q,
      SEARCH_LIMIT,
      0,
      undefined,
      project,
    )
    return res.canonicals.map((c) => ({ id: c.id, label: c.label }))
  }
  const res = await listCanonicalLocations(stylebookSlug, q, SEARCH_LIMIT, 0, undefined, project)
  return res.canonicals.map((c) => ({ id: c.id, label: c.label }))
}

/**
 * Live duplicate detection for canonical detail pages.
 *
 * Searches the catalog for the current label and keeps only strict
 * same-name-modulo-qualifiers matches (see `similarCanonicalMatch.ts`), so the
 * banner fires on "Kentucky" vs "Kentucky, US" but not on "Chicago, IL" vs
 * "O'Hare International Airport, Chicago, IL". Does not depend on cleanup
 * check runs. Ignores persist per canonical in localStorage.
 */
export function useSimilarCanonicalNotice(params: {
  stylebookSlug?: string
  canonicalId?: string
  canonicalLabel?: string
  entityType: CleanupEntityType
  project?: string
  enabled?: boolean
}) {
  const [loading, setLoading] = useState(false)
  const [matches, setMatches] = useState<SimilarCanonicalMatch[]>([])
  const [ignoredIds, setIgnoredIds] = useState<string[]>([])

  const normalizedLabel = (params.canonicalLabel ?? "").trim()
  const canonicalId = params.canonicalId
  const stylebookSlug = params.stylebookSlug
  const enabled = params.enabled ?? true

  useEffect(() => {
    setIgnoredIds(canonicalId ? readIgnoredIds(canonicalId) : [])
  }, [canonicalId])

  useEffect(() => {
    if (!enabled || !stylebookSlug || !canonicalId || !normalizedLabel) {
      setMatches([])
      setLoading(false)
      return
    }
    const query = duplicateSearchQuery(normalizedLabel)
    if (!query) {
      setMatches([])
      setLoading(false)
      return
    }
    let cancelled = false
    setLoading(true)
    void searchCanonicalsByType(params.entityType, stylebookSlug, query, params.project)
      .then((candidates) => {
        if (cancelled) return
        setMatches(
          candidates.filter(
            (candidate) =>
              candidate.id !== canonicalId &&
              isMaterialDuplicateLabel(normalizedLabel, candidate.label),
          ),
        )
      })
      .catch(() => {
        if (!cancelled) setMatches([])
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [enabled, stylebookSlug, canonicalId, normalizedLabel, params.entityType, params.project])

  const visibleMatches = useMemo(
    () => matches.filter((match) => !ignoredIds.includes(match.id)),
    [matches, ignoredIds],
  )

  const ignore = useCallback(() => {
    if (!canonicalId) return
    const next = [...new Set([...ignoredIds, ...matches.map((match) => match.id)])]
    setIgnoredIds(next)
    writeIgnoredIds(canonicalId, next)
  }, [canonicalId, ignoredIds, matches])

  return { loading, matches: visibleMatches, ignore }
}
