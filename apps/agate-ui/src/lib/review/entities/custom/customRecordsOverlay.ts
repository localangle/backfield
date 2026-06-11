/**
 * Draft overlay verbs for custom-record review edits (Custom tab edit path).
 *
 * Overlay schema under ``overlay.custom_records`` (payload-based identity:
 * record type + stable per-record key assigned at parse time):
 *
 *     {
 *       "<record_type>": {
 *         "by_key": { "<key>": { "fields": {...partial...}, "mentions": [...]? } },
 *         "removed_keys": ["<key>", ...],
 *         "user_added": [{ "key": "user_record:<uuid>", "fields": {...}, "mentions": [...], "source": "review" }]
 *       }
 *     }
 *
 * Mirrors ``api.processed_item.custom_records_merge`` on the API side.
 */

import type {
  CustomRecordMentionDisplay,
  CustomRecordRow,
  CustomRecordTableModel,
} from '@/lib/review/content/customRecordsDisplay'

export const USER_ADDED_RECORD_KEY_PREFIX = 'user_record:'

export function newUserAddedRecordKey(): string {
  const uuid =
    typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`
  return `${USER_ADDED_RECORD_KEY_PREFIX}${uuid}`
}

function cloneJson<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

type CustomTypeOverlay = {
  by_key: Record<string, Record<string, unknown>>
  removed_keys: string[]
  user_added: Record<string, unknown>[]
}

function emptyTypeOverlay(): CustomTypeOverlay {
  return { by_key: {}, removed_keys: [], user_added: [] }
}

function ensureCustomRecordType(
  draft: Record<string, unknown>,
  recordType: string,
): CustomTypeOverlay {
  if (!isPlainObject(draft.custom_records)) {
    draft.custom_records = {}
  }
  const root = draft.custom_records as Record<string, unknown>
  if (!isPlainObject(root[recordType])) {
    root[recordType] = emptyTypeOverlay()
  }
  const typeOverlay = root[recordType] as Record<string, unknown>
  if (!isPlainObject(typeOverlay.by_key)) typeOverlay.by_key = {}
  if (!Array.isArray(typeOverlay.removed_keys)) typeOverlay.removed_keys = []
  if (!Array.isArray(typeOverlay.user_added)) typeOverlay.user_added = []
  return typeOverlay as CustomTypeOverlay
}

function readTypeOverlay(
  overlay: Record<string, unknown> | null | undefined,
  recordType: string,
): CustomTypeOverlay {
  const normalized = emptyTypeOverlay()
  if (!isPlainObject(overlay) || !isPlainObject(overlay.custom_records)) return normalized
  const raw = (overlay.custom_records as Record<string, unknown>)[recordType]
  if (!isPlainObject(raw)) return normalized
  if (isPlainObject(raw.by_key)) {
    for (const [key, patch] of Object.entries(raw.by_key)) {
      if (key.trim() && isPlainObject(patch)) normalized.by_key[key] = patch
    }
  }
  if (Array.isArray(raw.removed_keys)) {
    normalized.removed_keys = raw.removed_keys.filter(
      (key): key is string => typeof key === 'string' && key.trim().length > 0,
    )
  }
  if (Array.isArray(raw.user_added)) {
    for (const row of raw.user_added) {
      if (
        isPlainObject(row) &&
        typeof row.key === 'string' &&
        row.key.trim() &&
        isPlainObject(row.fields)
      ) {
        normalized.user_added.push(row)
      }
    }
  }
  return normalized
}

/** True when the draft overlay carries any custom-record edits. */
export function customRecordsOverlayHasContent(
  overlay: Record<string, unknown> | null | undefined,
): boolean {
  if (!isPlainObject(overlay) || !isPlainObject(overlay.custom_records)) return false
  for (const recordType of Object.keys(overlay.custom_records as Record<string, unknown>)) {
    const typeOverlay = readTypeOverlay(overlay, recordType)
    if (
      Object.keys(typeOverlay.by_key).length > 0 ||
      typeOverlay.removed_keys.length > 0 ||
      typeOverlay.user_added.length > 0
    ) {
      return true
    }
  }
  return false
}

/** Merge a partial field patch into ``by_key[<key>].fields`` (model records). */
export function applyCustomRecordFieldsPatch(
  draft: Record<string, unknown>,
  recordType: string,
  recordKey: string,
  fields: Record<string, unknown>,
): Record<string, unknown> {
  const next = cloneJson(draft)
  const typeOverlay = ensureCustomRecordType(next, recordType)
  const current = typeOverlay.by_key[recordKey]
  const currentFields =
    isPlainObject(current) && isPlainObject(current.fields) ? current.fields : {}
  typeOverlay.by_key[recordKey] = {
    ...(isPlainObject(current) ? current : {}),
    fields: { ...currentFields, ...cloneJson(fields) },
  }
  return next
}

/** Replace the mention list in ``by_key[<key>].mentions`` (model records). */
export function applyCustomRecordMentionsPatch(
  draft: Record<string, unknown>,
  recordType: string,
  recordKey: string,
  mentions: CustomRecordMentionDisplay[],
): Record<string, unknown> {
  const next = cloneJson(draft)
  const typeOverlay = ensureCustomRecordType(next, recordType)
  const current = typeOverlay.by_key[recordKey]
  typeOverlay.by_key[recordKey] = {
    ...(isPlainObject(current) ? current : {}),
    mentions: cloneJson(mentions),
  }
  return next
}

/** Remove a record from review (model record hidden; reviewer-added record dropped). */
export function buildRemoveCustomRecordPatch(
  draft: Record<string, unknown>,
  recordType: string,
  recordKey: string,
  source: 'model' | 'review',
): Record<string, unknown> {
  const next = cloneJson(draft)
  const typeOverlay = ensureCustomRecordType(next, recordType)
  if (source === 'review') {
    typeOverlay.user_added = typeOverlay.user_added.filter((row) => row.key !== recordKey)
  } else {
    if (!typeOverlay.removed_keys.includes(recordKey)) {
      typeOverlay.removed_keys.push(recordKey)
    }
    delete typeOverlay.by_key[recordKey]
  }
  return next
}

/** Append or replace a reviewer-added record row (``source: "review"``). */
export function appendUserAddedCustomRecord(
  draft: Record<string, unknown>,
  recordType: string,
  row: {
    key: string
    fields: Record<string, unknown>
    mentions?: CustomRecordMentionDisplay[]
  },
): Record<string, unknown> {
  const next = cloneJson(draft)
  const typeOverlay = ensureCustomRecordType(next, recordType)
  const rest = typeOverlay.user_added.filter((entry) => entry.key !== row.key)
  typeOverlay.user_added = [
    ...rest,
    {
      key: row.key,
      fields: cloneJson(row.fields),
      mentions: cloneJson(row.mentions ?? []),
      source: 'review',
    },
  ]
  return next
}

/** Update fields/mentions on an existing reviewer-added record row. */
export function patchUserAddedCustomRecord(
  draft: Record<string, unknown>,
  recordType: string,
  recordKey: string,
  patch: { fields?: Record<string, unknown>; mentions?: CustomRecordMentionDisplay[] },
): Record<string, unknown> {
  const next = cloneJson(draft)
  const typeOverlay = ensureCustomRecordType(next, recordType)
  typeOverlay.user_added = typeOverlay.user_added.map((row) => {
    if (row.key !== recordKey) return row
    const updated: Record<string, unknown> = { ...row }
    if (patch.fields) {
      const currentFields = isPlainObject(row.fields) ? row.fields : {}
      updated.fields = { ...currentFields, ...cloneJson(patch.fields) }
    }
    if (patch.mentions) {
      updated.mentions = cloneJson(patch.mentions)
    }
    return updated
  })
  return next
}

function mentionsFromUnknown(raw: unknown): CustomRecordMentionDisplay[] {
  if (!Array.isArray(raw)) return []
  const mentions: CustomRecordMentionDisplay[] = []
  for (const entry of raw) {
    if (!isPlainObject(entry)) continue
    const text = typeof entry.text === 'string' ? entry.text.trim() : ''
    if (!text) continue
    mentions.push({ text, quote: false })
  }
  return mentions
}

function applyOverlayToRecord(
  record: CustomRecordRow,
  patch: Record<string, unknown>,
): CustomRecordRow {
  const next: CustomRecordRow = {
    ...record,
    fields: { ...record.fields },
    mentions: [...record.mentions],
  }
  if (isPlainObject(patch.fields)) {
    next.fields = { ...next.fields, ...cloneJson(patch.fields) }
  }
  if (Array.isArray(patch.mentions)) {
    next.mentions = mentionsFromUnknown(patch.mentions)
  }
  return next
}

/**
 * Apply draft overlay edits to display tables built from the **original** run output.
 * Mirrors the server-side reviewed-output merge so the draft view matches what saves.
 */
export function applyCustomRecordsOverlayToTables(
  tables: CustomRecordTableModel[],
  overlay: Record<string, unknown> | null | undefined,
): CustomRecordTableModel[] {
  return tables.map((table) => {
    const typeOverlay = readTypeOverlay(overlay, table.recordType)
    const removed = new Set(typeOverlay.removed_keys)
    const records: CustomRecordRow[] = []
    for (const record of table.records) {
      if (removed.has(record.key)) continue
      const patch = typeOverlay.by_key[record.key]
      records.push(patch ? applyOverlayToRecord(record, patch) : record)
    }
    const existingKeys = new Set(records.map((record) => record.key))
    for (const row of typeOverlay.user_added) {
      const key = typeof row.key === 'string' ? row.key : ''
      if (!key || existingKeys.has(key) || removed.has(key)) continue
      records.push({
        key,
        fields: isPlainObject(row.fields) ? cloneJson(row.fields) : {},
        mentions: mentionsFromUnknown(row.mentions),
        confidence: typeof row.confidence === 'number' ? row.confidence : null,
        source: 'review',
      })
    }
    return { ...table, records }
  })
}
