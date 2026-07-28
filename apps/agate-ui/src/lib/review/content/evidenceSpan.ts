/**
 * Map a place/location record from model output to character range(s) in the article body
 * for in-article verification highlights (Issue 6).
 */

export type EvidenceSpanReason = 'empty_body' | 'no_evidence' | 'not_in_story' | 'invalid_offsets'

export type EvidenceSpanRange = { start: number; end: number }

export type TieredHighlightRange = EvidenceSpanRange & { tier: 'ambient' | 'selected' | 'quote' }

/** Character range in the article with one or more geocoded place anchors. */
export type MentionSpanHit = EvidenceSpanRange & { anchors: string[] }

/** Mention range tied to a specific occurrence (for per-mention selection). */
export type OccurrenceSpanHit = MentionSpanHit & { occurrenceKey: string }

export type EvidenceSpansResult =
  | { kind: 'ranges'; ranges: EvidenceSpanRange[] }
  | { kind: 'none'; reason: EvidenceSpanReason }

/** @deprecated Prefer ``EvidenceSpansResult``; kept for callers that need a single range. */
export type EvidenceSpanResult =
  | { kind: 'range'; start: number; end: number }
  | { kind: 'none'; reason: EvidenceSpanReason }

function readSpanOffsetsFromLocation(loc: Record<string, unknown>): { start: number; end: number } | null {
  const components = loc.components
  if (!components || typeof components !== 'object' || Array.isArray(components)) {
    return null
  }
  const span = (components as Record<string, unknown>).span
  if (!span || typeof span !== 'object' || Array.isArray(span)) {
    return null
  }
  const s = span as Record<string, unknown>
  const startRaw = s.start ?? s.offset
  const endRaw = s.end
  const lengthRaw = s.length
  if (typeof startRaw !== 'number' || !Number.isFinite(startRaw)) {
    return null
  }
  const start = Math.trunc(startRaw)
  if (start < 0) {
    return null
  }
  let end: number
  if (typeof endRaw === 'number' && Number.isFinite(endRaw)) {
    end = Math.trunc(endRaw)
  } else if (typeof lengthRaw === 'number' && Number.isFinite(lengthRaw) && lengthRaw > 0) {
    end = start + Math.trunc(lengthRaw)
  } else {
    return null
  }
  if (end <= start) {
    return null
  }
  return { start, end }
}

function isValidRange(body: string, start: number, end: number): boolean {
  return start >= 0 && end <= body.length && end > start
}

/** Every non-overlapping occurrence of ``needle`` in ``articleBody`` (case-insensitive, UTF-16 indices). */
function findAllOriginalTextRanges(articleBody: string, needle: string): EvidenceSpanRange[] {
  const trimmed = needle.trim()
  if (!trimmed) {
    return []
  }
  const lowerBody = articleBody.toLowerCase()
  const lowerNeedle = trimmed.toLowerCase()
  const ranges: EvidenceSpanRange[] = []
  let searchFrom = 0
  while (searchFrom < articleBody.length) {
    const idx = lowerBody.indexOf(lowerNeedle, searchFrom)
    if (idx === -1) {
      break
    }
    const end = idx + trimmed.length
    ranges.push({ start: idx, end })
    searchFrom = end
  }
  return ranges
}

/**
 * All non-overlapping ``original_text`` occurrences for every needle (longest needles win overlaps).
 */
export function findAllMentionOccurrencesInArticle(
  articleBody: string,
  needles: string[],
): EvidenceSpanRange[] {
  if (typeof articleBody !== 'string' || articleBody.length === 0) {
    return []
  }
  const sortedNeedles = [...needles]
    .map((n) => n.trim())
    .filter((n) => n.length > 0)
    .sort((a, b) => b.length - a.length)

  const matches: EvidenceSpanRange[] = []
  for (const needle of sortedNeedles) {
    for (const range of findAllOriginalTextRanges(articleBody, needle)) {
      const overlaps = matches.findIndex((e) => range.start < e.end && range.end > e.start)
      if (overlaps >= 0) {
        const existing = matches[overlaps]!
        if (range.end - range.start > existing.end - existing.start) {
          matches[overlaps] = range
        }
      } else {
        matches.push(range)
      }
    }
  }
  return matches.sort((a, b) => a.start - b.start)
}

/** Merge ambient + selected + quote spans; quote wins over selected, selected wins over ambient. */
export function mergeTieredHighlightRanges(
  ambient: EvidenceSpanRange[],
  selected: EvidenceSpanRange[],
  quote: EvidenceSpanRange[] = [],
): TieredHighlightRange[] {
  type Ev = { pos: number; dSel: number; dAmb: number; dQuote: number }
  const events: Ev[] = []
  for (const r of ambient) {
    if (r.start < 0 || r.end <= r.start) continue
    events.push({ pos: r.start, dSel: 0, dAmb: 1, dQuote: 0 })
    events.push({ pos: r.end, dSel: 0, dAmb: -1, dQuote: 0 })
  }
  for (const r of selected) {
    if (r.start < 0 || r.end <= r.start) continue
    events.push({ pos: r.start, dSel: 1, dAmb: 0, dQuote: 0 })
    events.push({ pos: r.end, dSel: -1, dAmb: 0, dQuote: 0 })
  }
  for (const r of quote) {
    if (r.start < 0 || r.end <= r.start) continue
    events.push({ pos: r.start, dSel: 0, dAmb: 0, dQuote: 1 })
    events.push({ pos: r.end, dSel: 0, dAmb: 0, dQuote: -1 })
  }
  events.sort((a, b) => {
    if (a.pos !== b.pos) return a.pos - b.pos
    const aEnd = a.dSel < 0 || a.dAmb < 0 || a.dQuote < 0
    const bEnd = b.dSel < 0 || b.dAmb < 0 || b.dQuote < 0
    if (aEnd !== bEnd) return aEnd ? -1 : 1
    return 0
  })

  const out: TieredHighlightRange[] = []
  let sel = 0
  let amb = 0
  let quoteCount = 0
  let cursor = 0

  const tierAt = (): 'ambient' | 'selected' | 'quote' | null => {
    if (quoteCount > 0) return 'quote'
    if (sel > 0) return 'selected'
    if (amb > 0) return 'ambient'
    return null
  }

  for (const e of events) {
    const t = tierAt()
    if (t && e.pos > cursor) {
      out.push({ start: cursor, end: e.pos, tier: t })
    }
    cursor = e.pos
    sel += e.dSel
    amb += e.dAmb
    quoteCount += e.dQuote
  }

  return out
}

function mentionSpanKey(start: number, end: number): string {
  return `${start}:${end}`
}

/**
 * Map each resolved mention range to the geocoded place anchors that claim it.
 */
export type OccurrenceSpanInput = {
  clientId: string
  mentionText: string
  startChar: number | null
  endChar: number | null
  suppressed: boolean
}

function spanFromOccurrence(
  articleBody: string,
  occurrence: OccurrenceSpanInput,
): EvidenceSpanRange | null {
  if (occurrence.suppressed || !occurrence.mentionText.trim()) {
    return null
  }
  if (
    occurrence.startChar !== null &&
    occurrence.endChar !== null &&
    occurrence.endChar > occurrence.startChar &&
    occurrence.startChar >= 0 &&
    occurrence.endChar <= articleBody.length
  ) {
    return { start: occurrence.startChar, end: occurrence.endChar }
  }
  const ranges = findAllOriginalTextRanges(articleBody, occurrence.mentionText)
  return ranges[0] ?? null
}

/** Build span hits from explicit mention occurrences (preferred over ``original_text`` scan). */
export function buildOccurrenceSpanHits(
  articleBody: string,
  places: Array<{ anchor: string; occurrences: OccurrenceSpanInput[] }>,
): OccurrenceSpanHit[] {
  if (typeof articleBody !== 'string' || articleBody.length === 0) {
    return []
  }
  const hits: OccurrenceSpanHit[] = []
  for (const { anchor, occurrences } of places) {
    if (!anchor) continue
    for (const occ of occurrences) {
      const range = spanFromOccurrence(articleBody, occ)
      if (!range) continue
      hits.push({
        ...range,
        anchors: [anchor],
        occurrenceKey: `${anchor}:${occ.clientId}`,
      })
    }
  }
  return hits.sort((a, b) => a.start - b.start)
}

export function buildMentionSpanHits(
  articleBody: string,
  places: Array<{ anchor: string; location: Record<string, unknown> }>,
): MentionSpanHit[] {
  if (typeof articleBody !== 'string' || articleBody.length === 0) {
    return []
  }
  const byKey = new Map<string, Set<string>>()
  for (const { anchor, location } of places) {
    if (!anchor) continue
    const resolved = resolveEvidenceSpansInArticle(articleBody, location)
    if (resolved.kind !== 'ranges') continue
    for (const { start, end } of resolved.ranges) {
      const key = mentionSpanKey(start, end)
      let anchors = byKey.get(key)
      if (!anchors) {
        anchors = new Set()
        byKey.set(key, anchors)
      }
      anchors.add(anchor)
    }
  }
  return [...byKey.entries()]
    .map(([key, anchors]) => {
      const [startStr, endStr] = key.split(':')
      return {
        start: Number(startStr),
        end: Number(endStr),
        anchors: [...anchors].sort(),
      }
    })
    .sort((a, b) => a.start - b.start)
}

/** Anchors for geocoded places whose mention range overlaps ``[start, end)``. */
export function collectAnchorsForRange(
  hits: MentionSpanHit[],
  start: number,
  end: number,
): string[] {
  const set = new Set<string>()
  for (const hit of hits) {
    if (hit.start < end && hit.end > start) {
      for (const anchor of hit.anchors) {
        set.add(anchor)
      }
    }
  }
  return [...set].sort()
}

/**
 * Resolve UTF-16 highlight ranges in ``articleBody`` for a place row.
 * Uses explicit ``components.span`` when valid (single range); otherwise all matches of trimmed ``original_text``.
 */
export function resolveEvidenceSpansInArticle(
  articleBody: string,
  location: Record<string, unknown> | null | undefined,
): EvidenceSpansResult {
  if (typeof articleBody !== 'string' || articleBody.length === 0) {
    return { kind: 'none', reason: 'empty_body' }
  }
  if (!location || typeof location !== 'object') {
    return { kind: 'none', reason: 'no_evidence' }
  }

  const explicit = readSpanOffsetsFromLocation(location)
  if (explicit) {
    const { start, end } = explicit
    if (isValidRange(articleBody, start, end)) {
      return { kind: 'ranges', ranges: [{ start, end }] }
    }
    const fromText = findAllOriginalTextRanges(
      articleBody,
      typeof location.original_text === 'string' ? location.original_text : '',
    )
    if (fromText.length > 0) {
      return { kind: 'ranges', ranges: fromText }
    }
    return { kind: 'none', reason: 'invalid_offsets' }
  }

  const ot = location.original_text
  if (typeof ot !== 'string' || !ot.trim()) {
    return { kind: 'none', reason: 'no_evidence' }
  }
  const ranges = findAllOriginalTextRanges(articleBody, ot)
  if (ranges.length === 0) {
    return { kind: 'none', reason: 'not_in_story' }
  }
  return { kind: 'ranges', ranges }
}

/**
 * First highlight range only (legacy helper).
 */
export function resolveEvidenceSpanInArticle(
  articleBody: string,
  location: Record<string, unknown> | null | undefined,
): EvidenceSpanResult {
  const multi = resolveEvidenceSpansInArticle(articleBody, location)
  if (multi.kind === 'ranges' && multi.ranges.length > 0) {
    const first = multi.ranges[0]!
    return { kind: 'range', start: first.start, end: first.end }
  }
  return { kind: 'none', reason: multi.kind === 'none' ? multi.reason : 'no_evidence' }
}
