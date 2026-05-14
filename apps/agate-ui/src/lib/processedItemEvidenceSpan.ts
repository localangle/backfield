/**
 * Map a place/location record from model output to a character range in the article body
 * for in-article verification highlights (Issue 6).
 */

export type EvidenceSpanReason = 'empty_body' | 'no_evidence' | 'not_in_story' | 'invalid_offsets'

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

function tryOriginalTextRange(articleBody: string, location: Record<string, unknown>): EvidenceSpanResult | null {
  const ot = location.original_text
  if (typeof ot !== 'string') {
    return null
  }
  const needle = ot.trim()
  if (!needle) {
    return null
  }
  const idx = articleBody.indexOf(needle)
  if (idx === -1) {
    return { kind: 'none', reason: 'not_in_story' }
  }
  return { kind: 'range', start: idx, end: idx + needle.length }
}

/**
 * Resolve a UTF-16 code unit range in ``articleBody`` for evidence highlighting.
 * Prefer explicit ``components.span`` when valid for the body; otherwise first exact match of trimmed ``original_text``.
 * If span hints are present but out of range, ``original_text`` is still tried when it matches the story.
 */
export function resolveEvidenceSpanInArticle(
  articleBody: string,
  location: Record<string, unknown> | null | undefined,
): EvidenceSpanResult {
  if (typeof articleBody !== 'string' || articleBody.length === 0) {
    return { kind: 'none', reason: 'empty_body' }
  }
  if (!location || typeof location !== 'object') {
    return { kind: 'none', reason: 'no_evidence' }
  }

  const explicit = readSpanOffsetsFromLocation(location)
  if (explicit) {
    const { start, end } = explicit
    if (start >= 0 && end <= articleBody.length && end > start) {
      return { kind: 'range', start, end }
    }
    const fallback = tryOriginalTextRange(articleBody, location)
    if (fallback && fallback.kind === 'range') {
      return fallback
    }
    return { kind: 'none', reason: 'invalid_offsets' }
  }

  const fromText = tryOriginalTextRange(articleBody, location)
  if (fromText) {
    return fromText
  }
  return { kind: 'none', reason: 'no_evidence' }
}
