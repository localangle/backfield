/**
 * Map ``custom_records`` blocks from run output to display table models for the
 * processed-item Custom review tab (one table per record type).
 */

import {
  findAllMentionOccurrencesInArticle,
  type EvidenceSpanRange,
} from '@/lib/review/content/evidenceSpan'

export type CustomRecordColumn = {
  name: string
  label: string
  type: string
}

export type CustomRecordMentionDisplay = {
  text: string
  quote: boolean
}

export type CustomRecordRow = {
  key: string
  fields: Record<string, unknown>
  mentions: CustomRecordMentionDisplay[]
  confidence: number | null
  /** Reviewer-added records carry review provenance; model records came from the flow. */
  source: 'model' | 'review'
}

export type CustomRecordTableModel = {
  recordType: string
  label: string
  columns: CustomRecordColumn[]
  records: CustomRecordRow[]
  droppedUngrounded: number
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function readCustomRecordsBlock(payload: Record<string, unknown>): Record<string, unknown> | null {
  const direct = payload.custom_records
  if (isPlainObject(direct)) return direct
  const consolidated = payload.consolidated
  if (isPlainObject(consolidated) && isPlainObject(consolidated.custom_records)) {
    return consolidated.custom_records
  }
  return null
}

/**
 * Collect the union of ``custom_records`` blocks across all node payloads in run output.
 * Later payloads win per record type (DBOutput consolidated payloads carry the merged set).
 */
export function extractCustomRecordsBlock(
  output: Record<string, unknown> | null | undefined,
): Record<string, unknown> {
  const merged: Record<string, unknown> = {}
  if (!isPlainObject(output)) return merged
  for (const payload of Object.values(output)) {
    if (!isPlainObject(payload)) continue
    const block = readCustomRecordsBlock(payload)
    if (!block) continue
    for (const [recordType, recordSet] of Object.entries(block)) {
      if (isPlainObject(recordSet)) {
        merged[recordType] = recordSet
      }
    }
  }
  return merged
}

function normalizeColumns(raw: unknown): CustomRecordColumn[] {
  if (!Array.isArray(raw)) return []
  const columns: CustomRecordColumn[] = []
  for (const entry of raw) {
    if (!isPlainObject(entry)) continue
    const name = typeof entry.name === 'string' ? entry.name : ''
    if (!name) continue
    columns.push({
      name,
      label:
        typeof entry.label === 'string' && entry.label.trim()
          ? entry.label
          : name.replace(/_/g, ' '),
      type: typeof entry.type === 'string' ? entry.type : 'string',
    })
  }
  return columns
}

function normalizeMentions(raw: unknown): CustomRecordMentionDisplay[] {
  if (!Array.isArray(raw)) return []
  const mentions: CustomRecordMentionDisplay[] = []
  for (const entry of raw) {
    if (typeof entry === 'string') {
      if (entry.trim()) mentions.push({ text: entry.trim(), quote: false })
      continue
    }
    if (!isPlainObject(entry)) continue
    const text = typeof entry.text === 'string' ? entry.text.trim() : ''
    if (!text) continue
    mentions.push({ text, quote: false })
  }
  return mentions
}

function normalizeRecords(raw: unknown, recordType: string): CustomRecordRow[] {
  if (!Array.isArray(raw)) return []
  const records: CustomRecordRow[] = []
  for (const [index, entry] of raw.entries()) {
    if (!isPlainObject(entry)) continue
    const fields = isPlainObject(entry.fields) ? entry.fields : {}
    records.push({
      key: typeof entry.key === 'string' && entry.key ? entry.key : `${recordType}-${index}`,
      fields,
      mentions: normalizeMentions(entry.mentions),
      confidence: typeof entry.confidence === 'number' ? entry.confidence : null,
      source: entry.source === 'review' ? 'review' : 'model',
    })
  }
  return records
}

function recordTypeDisplayLabel(recordType: string, raw: unknown): string {
  if (typeof raw === 'string' && raw.trim()) return raw.trim()
  return recordType.replace(/_/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

/** One display table per record type from a run-output dict (reviewed or original). */
export function buildCustomRecordTables(
  output: Record<string, unknown> | null | undefined,
): CustomRecordTableModel[] {
  const block = extractCustomRecordsBlock(output)
  const tables: CustomRecordTableModel[] = []
  for (const [recordType, recordSetRaw] of Object.entries(block)) {
    if (!isPlainObject(recordSetRaw)) continue
    tables.push({
      recordType,
      label: recordTypeDisplayLabel(recordType, recordSetRaw.label),
      columns: normalizeColumns(recordSetRaw.schema),
      records: normalizeRecords(recordSetRaw.records, recordType),
      droppedUngrounded:
        typeof recordSetRaw.dropped_ungrounded === 'number' ? recordSetRaw.dropped_ungrounded : 0,
    })
  }
  return tables
}

export type CustomRecordConfidenceTier = 'high' | 'medium' | 'low'

/** Map a numeric confidence score to High (≥0.9), Medium (≥0.7), or Low. */
export function customRecordConfidenceTier(
  value: number | null,
): CustomRecordConfidenceTier | null {
  if (value === null || !Number.isFinite(value)) return null
  if (value >= 0.9) return 'high'
  if (value >= 0.7) return 'medium'
  return 'low'
}

export function customRecordConfidenceLabel(value: number | null): string | null {
  const tier = customRecordConfidenceTier(value)
  if (!tier) return null
  return tier.charAt(0).toUpperCase() + tier.slice(1)
}

/** User-facing cell text for a field value (lists handled separately as chips). */
export function customRecordCellText(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (Array.isArray(value)) return value.map((item) => String(item)).join(', ')
  return String(value)
}

/** List items for chip rendering when the field value is a list. */
export function customRecordCellListItems(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null
  const items = value.map((item) => String(item)).filter((item) => item.trim() !== '')
  return items.length > 0 ? items : null
}

/** Highlight ranges for one mention's text in the article body (all occurrences). */
export function customMentionHighlightRanges(
  articleBody: string,
  mentionText: string,
): EvidenceSpanRange[] {
  if (typeof articleBody !== 'string' || !articleBody || !mentionText.trim()) return []
  return findAllMentionOccurrencesInArticle(articleBody, [mentionText])
}

/** Ambient highlight ranges for every mention across all custom record tables. */
export function customAmbientHighlightRanges(
  articleBody: string,
  tables: CustomRecordTableModel[],
): EvidenceSpanRange[] {
  if (typeof articleBody !== 'string' || !articleBody) return []
  const needles: string[] = []
  for (const table of tables) {
    for (const record of table.records) {
      for (const mention of record.mentions) {
        if (mention.text.trim()) needles.push(mention.text.trim())
      }
    }
  }
  return findAllMentionOccurrencesInArticle(articleBody, needles)
}
