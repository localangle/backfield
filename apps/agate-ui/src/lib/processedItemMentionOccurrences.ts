/**
 * Mention occurrence drafts for processed-item Review (story quotes per place).
 */

import { findAllMentionOccurrencesInArticle } from './processedItemEvidenceSpan'

export type MentionOccurrenceDraft = {
  /** DB id when persisted. */
  id?: number
  /** Stable client id for new rows before save. */
  clientId: string
  mentionText: string
  startChar: number | null
  endChar: number | null
  occurrenceOrder: number
  suppressed: boolean
}

export type MergedRowWithOccurrences = {
  location?: Record<string, unknown>
  mention_occurrences?: unknown
}

function newClientId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `occ-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function normalizeApiOccurrence(raw: Record<string, unknown>, order: number): MentionOccurrenceDraft | null {
  const textRaw = raw.mention_text ?? raw.text
  const mentionText = typeof textRaw === 'string' ? textRaw.trim() : ''
  if (!mentionText) return null
  const idRaw = raw.id
  const id = typeof idRaw === 'number' && Number.isFinite(idRaw) ? Math.trunc(idRaw) : undefined
  const clientRaw = raw.client_id
  const clientId =
    typeof clientRaw === 'string' && clientRaw.trim() ? clientRaw.trim() : id !== undefined ? `id:${id}` : newClientId()
  const startRaw = raw.start_char
  const endRaw = raw.end_char
  const orderRaw = raw.occurrence_order
  return {
    id,
    clientId,
    mentionText,
    startChar: typeof startRaw === 'number' && Number.isFinite(startRaw) ? Math.trunc(startRaw) : null,
    endChar: typeof endRaw === 'number' && Number.isFinite(endRaw) ? Math.trunc(endRaw) : null,
    occurrenceOrder: typeof orderRaw === 'number' && Number.isFinite(orderRaw) ? Math.trunc(orderRaw) : order,
    suppressed: Boolean(raw.suppressed),
  }
}

function occurrenceSourceKind(raw: Record<string, unknown>): string {
  const source = raw.source_kind
  return typeof source === 'string' ? source.trim() : ''
}

function modelOccurrencesFromPlace(place: Record<string, unknown>): MentionOccurrenceDraft[] {
  const mentions = place.mentions
  if (Array.isArray(mentions)) {
    const out: MentionOccurrenceDraft[] = []
    for (let i = 0; i < mentions.length; i++) {
      const item = mentions[i]
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        const text = (item as Record<string, unknown>).text
        const norm = normalizeApiOccurrence({ text, mention_text: text }, i)
        if (norm) out.push(norm)
      } else if (typeof item === 'string' && item.trim()) {
        const norm = normalizeApiOccurrence({ text: item, mention_text: item }, i)
        if (norm) out.push(norm)
      }
    }
    if (out.length > 0) return out
  }
  const ot = place.original_text
  if (typeof ot === 'string' && ot.trim()) {
    return [
      {
        clientId: newClientId(),
        mentionText: ot.trim(),
        startChar: null,
        endChar: null,
        occurrenceOrder: 0,
        suppressed: false,
      },
    ]
  }
  return []
}

function shouldPreferModelOccurrences(
  apiRows: Record<string, unknown>[],
  apiOccurrences: MentionOccurrenceDraft[],
  modelOccurrences: MentionOccurrenceDraft[],
): boolean {
  if (apiOccurrences.length === 0 || modelOccurrences.length === 0) return false
  const allSystem = apiRows.every((raw) => {
    const source = occurrenceSourceKind(raw)
    return source === '' || source === 'model' || source === 'system_extraction'
  })
  if (!allSystem) return false
  const modelTexts = new Set(modelOccurrences.map((o) => o.mentionText.trim().toLowerCase()).filter(Boolean))
  return apiOccurrences.every((occ) => !modelTexts.has(occ.mentionText.trim().toLowerCase()))
}

/** Read occurrences from merged row (API ``mention_occurrences`` or place ``mentions``). */
export function readMentionOccurrencesFromRow(
  row: MergedRowWithOccurrences | null | undefined,
): MentionOccurrenceDraft[] {
  if (!row) return []
  const place = row.location
  const modelOccurrences =
    place && typeof place === 'object' ? modelOccurrencesFromPlace(place) : []
  const rawList = row.mention_occurrences
  if (Array.isArray(rawList)) {
    const out: MentionOccurrenceDraft[] = []
    const apiRows: Record<string, unknown>[] = []
    for (let i = 0; i < rawList.length; i++) {
      const item = rawList[i]
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        const raw = item as Record<string, unknown>
        apiRows.push(raw)
        const norm = normalizeApiOccurrence(raw, i)
        if (norm) out.push(norm)
      }
    }
    if (out.length > 0) {
      if (shouldPreferModelOccurrences(apiRows, out, modelOccurrences)) {
        return modelOccurrences
      }
      return out.sort((a, b) => a.occurrenceOrder - b.occurrenceOrder)
    }
  }
  return modelOccurrences
}

export function activeMentionOccurrences(occurrences: MentionOccurrenceDraft[]): MentionOccurrenceDraft[] {
  return occurrences.filter((o) => !o.suppressed).sort((a, b) => a.occurrenceOrder - b.occurrenceOrder)
}

export function mentionOccurrencesEqual(a: MentionOccurrenceDraft[], b: MentionOccurrenceDraft[]): boolean {
  const norm = (list: MentionOccurrenceDraft[]) =>
    JSON.stringify(
      list.map((o) => ({
        id: o.id,
        clientId: o.clientId,
        mentionText: o.mentionText,
        startChar: o.startChar,
        endChar: o.endChar,
        occurrenceOrder: o.occurrenceOrder,
        suppressed: o.suppressed,
      })),
    )
  return norm(a) === norm(b)
}

export function resolveOccurrenceSpansInArticle(
  articleBody: string,
  occurrence: MentionOccurrenceDraft,
): { start: number; end: number } | null {
  if (
    occurrence.startChar !== null &&
    occurrence.endChar !== null &&
    occurrence.endChar > occurrence.startChar &&
    occurrence.startChar >= 0 &&
    occurrence.endChar <= articleBody.length
  ) {
    return { start: occurrence.startChar, end: occurrence.endChar }
  }
  const ranges = findAllMentionOccurrencesInArticle(articleBody, [occurrence.mentionText])
  if (ranges.length === 0) return null
  const first = ranges[0]!
  return { start: first.start, end: first.end }
}

export function recomputeOccurrenceSpans(
  articleBody: string,
  occurrences: MentionOccurrenceDraft[],
): MentionOccurrenceDraft[] {
  const usedEnds = new Map<string, number>()
  return occurrences.map((occ) => {
    if (occ.suppressed) return occ
    const key = occ.mentionText.toLowerCase()
    const searchFrom = usedEnds.get(key) ?? 0
    const ranges = findAllMentionOccurrencesInArticle(articleBody, [occ.mentionText])
    const match = ranges.find((r) => r.start >= searchFrom) ?? ranges[0]
    if (!match) {
      return { ...occ, startChar: null, endChar: null }
    }
    usedEnds.set(key, match.end)
    return { ...occ, startChar: match.start, endChar: match.end }
  })
}

export function createEmptyMentionOccurrence(order: number): MentionOccurrenceDraft {
  return {
    clientId: newClientId(),
    mentionText: '',
    startChar: null,
    endChar: null,
    occurrenceOrder: order,
    suppressed: false,
  }
}

export function buildOccurrencesOverlayPayload(occurrences: MentionOccurrenceDraft[]): Record<string, unknown>[] {
  return occurrences.map((o, i) => {
    const row: Record<string, unknown> = {
      client_id: o.clientId,
      mention_text: o.mentionText.trim(),
      start_char: o.startChar,
      end_char: o.endChar,
      occurrence_order: o.occurrenceOrder ?? i,
      suppressed: o.suppressed,
    }
    if (o.id !== undefined) row.id = o.id
    return row
  })
}

export function primaryMentionText(occurrences: MentionOccurrenceDraft[]): string {
  const active = activeMentionOccurrences(occurrences)
  return active[0]?.mentionText.trim() ?? ''
}
