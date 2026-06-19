/** Label similarity helpers for Stylebook candidate create + post-create link prompts. */

import { suggestedRowAction } from "@/lib/candidateQueueSuggestions"

export const CREATE_LINK_NUDGE_MIN_SCORE = 0.86

export function normalizeLabelForCompare(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ")
}

function diceBigramCoefficient(a: string, b: string): number {
  if (a.length < 2 || b.length < 2) return 0
  const bigrams = (s: string) => {
    const arr: string[] = []
    for (let i = 0; i < s.length - 1; i++) arr.push(s.slice(i, i + 2))
    return arr
  }
  const A = bigrams(a)
  const B = bigrams(b)
  const counts = new Map<string, number>()
  for (const g of A) counts.set(g, (counts.get(g) ?? 0) + 1)
  let inter = 0
  for (const g of B) {
    const n = counts.get(g) ?? 0
    if (n > 0) {
      inter++
      counts.set(g, n - 1)
    }
  }
  return (2 * inter) / (A.length + B.length)
}

/** 0–1 similarity for comparing a draft canonical label to an existing catalog label. */
export function stringSimilarityForLabels(draft: string, candidateLabel: string): number {
  const d = normalizeLabelForCompare(draft)
  const c = normalizeLabelForCompare(candidateLabel)
  if (!d || !c) return 0
  if (d === c) return 1
  if (d.includes(c) || c.includes(d)) return 0.93
  return diceBigramCoefficient(d, c)
}

function similarityRankScore(label: string, needleRaw: string): number {
  const name = normalizeLabelForCompare(label)
  const needle = normalizeLabelForCompare(needleRaw)
  if (!name || !needle) return 0
  if (name === needle) return 1_000_000
  if (name.startsWith(needle) || needle.startsWith(name)) return 500_000
  if (name.includes(needle) || needle.includes(name)) return 200_000
  const ta = new Set(name.split(/[\s,]+/).filter(Boolean))
  const tb = new Set(needle.split(/[\s,]+/).filter(Boolean))
  let inter = 0
  for (const t of ta) if (tb.has(t)) inter++
  const union = ta.size + tb.size - inter
  const jaccard = union === 0 ? 0 : inter / union
  return jaccard * 10_000 + diceBigramCoefficient(name, needle) * 1000
}

/** Rank queue rows by how closely their display label matches a search needle. */
export function rankCandidatesByLabelSimilarity<T>(
  rows: T[],
  needle: string,
  getLabel: (row: T) => string,
): T[] {
  const scored = rows.map((row) => ({
    row,
    s: similarityRankScore(getLabel(row), needle),
  }))
  scored.sort((a, b) => {
    if (b.s !== a.s) return b.s - a.s
    return normalizeLabelForCompare(getLabel(a.row)).localeCompare(
      normalizeLabelForCompare(getLabel(b.row)),
    )
  })
  return scored.map((x) => x.row)
}

export type SimilarCanonicalPick = {
  canonicalId: string
  label: string
  score: number
}

/** Best catalog suggestion when draft label is very close to an existing canonical. */
export function pickCreateLinkNudge(
  suggestions: ReadonlyArray<{ canonical_id: string; label: string }>,
  draftLabel: string,
  minScore: number = CREATE_LINK_NUDGE_MIN_SCORE,
): SimilarCanonicalPick | null {
  let best: SimilarCanonicalPick | null = null
  for (const s of suggestions) {
    const score = stringSimilarityForLabels(draftLabel, s.label)
    if (!best || score > best.score) {
      best = { canonicalId: s.canonical_id, label: s.label, score }
    }
  }
  if (best && best.score >= minScore) return best
  return null
}

/** Normalized key for comparing candidate display names within a queue page or batch. */
export function candidateQueueNameKey(displayName: string): string {
  return normalizeLabelForCompare(displayName)
}

export type DuplicateCreateNewCluster = {
  nameKey: string
  displayName: string
  count: number
}

export type DuplicateCreateNewSummary = {
  clusters: DuplicateCreateNewCluster[]
  /** Names that appear more than once with a create-new suggestion. */
  duplicateNameCount: number
  /** Rows beyond the first per duplicate name (e.g. 3 rows for one name → 2 extra). */
  totalExtraRows: number
}

/** Group open-queue rows that share a name and both suggest creating a new canonical. */
export function duplicateCreateNewClusters<T>(
  candidates: T[],
  getDisplayName: (candidate: T) => string,
): DuplicateCreateNewCluster[] {
  const groups = new Map<string, { displayName: string; count: number }>()
  for (const candidate of candidates) {
    if (suggestedRowAction(candidate) !== "create_new") continue
    const displayName = getDisplayName(candidate).trim()
    const nameKey = candidateQueueNameKey(displayName)
    if (!nameKey) continue
    const existing = groups.get(nameKey)
    if (existing) {
      existing.count += 1
    } else {
      groups.set(nameKey, { displayName, count: 1 })
    }
  }
  return [...groups.entries()]
    .filter(([, group]) => group.count > 1)
    .map(([nameKey, group]) => ({
      nameKey,
      displayName: group.displayName,
      count: group.count,
    }))
    .sort(
      (a, b) =>
        b.count - a.count ||
        normalizeLabelForCompare(a.displayName).localeCompare(
          normalizeLabelForCompare(b.displayName),
        ),
    )
}

export function duplicateCreateNewSummary<T>(
  candidates: T[],
  getDisplayName: (candidate: T) => string,
): DuplicateCreateNewSummary {
  const clusters = duplicateCreateNewClusters(candidates, getDisplayName)
  const duplicateNameCount = clusters.length
  const totalExtraRows = clusters.reduce((sum, cluster) => sum + cluster.count - 1, 0)
  return { clusters, duplicateNameCount, totalExtraRows }
}
