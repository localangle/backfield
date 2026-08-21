/** Set on node data while the JSON editor content fails validation (not persisted on save). */
export const JSON_INPUT_INVALID_MARKER = '__jsonInputInvalid'

export const JSON_INPUT_DOCUMENTS_KEY = 'documents'
export const JSON_INPUT_SOURCE_FILE_KEY = 'source_file'
export const JSON_INPUT_MAX_DOCUMENTS = 20
export const JSON_INPUT_PUBLIC_ALIAS_KEY = 'public_alias'

const NODE_LEVEL_KEYS = new Set([
  JSON_INPUT_INVALID_MARKER,
  JSON_INPUT_DOCUMENTS_KEY,
  JSON_INPUT_PUBLIC_ALIAS_KEY,
  'onChange',
])

export type JsonInputDocument = Record<string, unknown> & {
  text: string
  source_file?: string
}

export function jsonInputInvalidNodeData(
  existing?: Record<string, unknown>,
): Record<string, unknown> {
  return { ...(existing ?? {}), [JSON_INPUT_INVALID_MARKER]: true }
}

export function markJsonInputNodeDataInvalid(
  data: Record<string, unknown> | undefined,
): Record<string, unknown> {
  return jsonInputInvalidNodeData(data)
}

export function isJsonInputInvalidNodeData(data: unknown): boolean {
  return (
    typeof data === 'object' &&
    data !== null &&
    !Array.isArray(data) &&
    (data as Record<string, unknown>)[JSON_INPUT_INVALID_MARKER] === true
  )
}

export function stripJsonInputEditorMarkers(
  params: Record<string, unknown>,
): Record<string, unknown> {
  const out = { ...params }
  delete out[JSON_INPUT_INVALID_MARKER]
  return out
}

function isDocumentObject(value: unknown): value is JsonInputDocument {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    return false
  }
  const rec = value as Record<string, unknown>
  if (!('text' in rec)) return false
  return typeof rec.text === 'string'
}

/** Valid JSON Input node data: flat object or multi-file ``documents`` (2–20). */
export function isValidJsonInputData(
  data: unknown,
): data is Record<string, unknown> & { text?: string; documents?: JsonInputDocument[] } {
  if (isJsonInputInvalidNodeData(data)) {
    return false
  }
  if (typeof data !== 'object' || data === null || Array.isArray(data)) {
    return false
  }
  const rec = data as Record<string, unknown>
  const docs = rec[JSON_INPUT_DOCUMENTS_KEY]
  if (docs !== undefined) {
    if (!Array.isArray(docs)) return false
    if (docs.length < 2 || docs.length > JSON_INPUT_MAX_DOCUMENTS) return false
    return docs.every((entry) => {
      if (!isDocumentObject(entry)) return false
      const name = entry[JSON_INPUT_SOURCE_FILE_KEY]
      return name === undefined || typeof name === 'string'
    })
  }
  if (!('text' in rec)) {
    return false
  }
  return typeof rec.text === 'string'
}

export type JsonInputParseResult =
  | { ok: true; data: Record<string, unknown> & { text: string } }
  | { ok: false; error: string }

/** Parse editor JSON; rejects invalid syntax or missing/non-string `text`. */
export function parseJsonInputEditorText(value: string): JsonInputParseResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(value) as unknown
  } catch {
    return { ok: false, error: 'Invalid JSON syntax' }
  }

  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return { ok: false, error: 'JSON must be an object' }
  }

  const rec = parsed as Record<string, unknown>
  if (!('text' in rec)) {
    return { ok: false, error: 'JSON must include a "text" field' }
  }
  if (typeof rec.text !== 'string') {
    return { ok: false, error: '"text" must be a string' }
  }

  return { ok: true, data: rec as Record<string, unknown> & { text: string } }
}

export function articleFieldsFromNodeData(
  data: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(data)) {
    if (NODE_LEVEL_KEYS.has(key)) continue
    out[key] = value
  }
  return out
}

export function getJsonInputDocumentList(
  data: Record<string, unknown> | undefined,
): JsonInputDocument[] {
  if (!data) return [{ text: '' }]
  const docs = data[JSON_INPUT_DOCUMENTS_KEY]
  if (Array.isArray(docs) && docs.length >= 2) {
    return docs.filter(isDocumentObject).map((entry) => {
      const source =
        typeof entry[JSON_INPUT_SOURCE_FILE_KEY] === 'string' &&
        entry[JSON_INPUT_SOURCE_FILE_KEY].trim()
          ? String(entry[JSON_INPUT_SOURCE_FILE_KEY]).trim()
          : 'document.json'
      return { ...entry, [JSON_INPUT_SOURCE_FILE_KEY]: source, text: entry.text }
    })
  }
  const flat = articleFieldsFromNodeData(data)
  const text = typeof flat.text === 'string' ? flat.text : ''
  return [{ ...flat, text }]
}

export function isJsonInputMultiDocument(
  data: Record<string, unknown> | undefined,
): boolean {
  const docs = data?.[JSON_INPUT_DOCUMENTS_KEY]
  return Array.isArray(docs) && docs.length >= 2
}

function preserveNodeLevelFields(
  data: Record<string, unknown> | undefined,
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  if (!data) return out
  if (typeof data[JSON_INPUT_PUBLIC_ALIAS_KEY] === 'string') {
    out[JSON_INPUT_PUBLIC_ALIAS_KEY] = data[JSON_INPUT_PUBLIC_ALIAS_KEY]
  }
  return out
}

/** Build node data from one or more documents; collapses length ≤1 to flat params. */
export function buildJsonInputNodeData(
  documents: JsonInputDocument[],
  previous?: Record<string, unknown>,
): Record<string, unknown> {
  const preserved = preserveNodeLevelFields(previous)
  if (documents.length === 0) {
    return { ...preserved, text: '' }
  }
  if (documents.length === 1) {
    const only = documents[0]
    const fields: Record<string, unknown> = { ...only }
    delete fields[JSON_INPUT_SOURCE_FILE_KEY]
    delete fields[JSON_INPUT_DOCUMENTS_KEY]
    return { ...preserved, ...fields, text: typeof only.text === 'string' ? only.text : '' }
  }
  const capped = documents.slice(0, JSON_INPUT_MAX_DOCUMENTS).map((doc, index) => {
    const source =
      typeof doc[JSON_INPUT_SOURCE_FILE_KEY] === 'string' &&
      String(doc[JSON_INPUT_SOURCE_FILE_KEY]).trim()
        ? String(doc[JSON_INPUT_SOURCE_FILE_KEY]).trim()
        : `document-${index + 1}.json`
    const fields: Record<string, unknown> = { ...doc, [JSON_INPUT_SOURCE_FILE_KEY]: source }
    delete fields[JSON_INPUT_DOCUMENTS_KEY]
    return fields
  })
  return { ...preserved, [JSON_INPUT_DOCUMENTS_KEY]: capped }
}

/** Normalize saved params: collapse length-1 documents; drop invalid marker. */
export function normalizeJsonInputParamsForSave(
  params: Record<string, unknown>,
): Record<string, unknown> {
  const stripped = stripJsonInputEditorMarkers(params)
  const docs = stripped[JSON_INPUT_DOCUMENTS_KEY]
  if (!Array.isArray(docs)) {
    return stripped
  }
  if (docs.length <= 1) {
    return buildJsonInputNodeData(
      docs.filter(isDocumentObject).map((d) => ({ ...d, text: d.text })),
      stripped,
    )
  }
  if (docs.length > JSON_INPUT_MAX_DOCUMENTS) {
    return buildJsonInputNodeData(
      docs
        .filter(isDocumentObject)
        .slice(0, JSON_INPUT_MAX_DOCUMENTS)
        .map((d) => ({ ...d, text: d.text })),
      stripped,
    )
  }
  return stripped
}

export type JsonFileParseResult =
  | { ok: true; document: JsonInputDocument }
  | { ok: false; error: string }

/** Parse an uploaded file body into a JSON Input document (plain-language errors). */
export function parseJsonInputFileText(
  raw: string,
  fileName: string,
): JsonFileParseResult {
  let parsed: unknown
  try {
    parsed = JSON.parse(raw) as unknown
  } catch {
    return { ok: false, error: `“${fileName}” is not valid JSON.` }
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
    return {
      ok: false,
      error: `“${fileName}” must contain a single JSON object.`,
    }
  }
  const rec = parsed as Record<string, unknown>
  if (!('text' in rec) || typeof rec.text !== 'string') {
    return {
      ok: false,
      error: `“${fileName}” needs a text field (a string, which may be empty).`,
    }
  }
  const baseName = fileName.trim() || 'document.json'
  return {
    ok: true,
    document: {
      ...rec,
      text: rec.text,
      [JSON_INPUT_SOURCE_FILE_KEY]: baseName,
    },
  }
}

function flatHasUserContent(data: Record<string, unknown>): boolean {
  const fields = articleFieldsFromNodeData(data)
  if (typeof fields.text === 'string' && fields.text.trim()) return true
  return Object.keys(fields).some((key) => key !== 'text')
}

/**
 * Merge newly parsed uploads into node data.
 * One file on a flat node replaces content; additional files promote to ``documents``.
 */
export function mergeJsonInputUploads(
  current: Record<string, unknown> | undefined,
  uploads: JsonInputDocument[],
): { ok: true; data: Record<string, unknown> } | { ok: false; error: string } {
  if (uploads.length === 0) {
    return { ok: false, error: 'Choose at least one JSON file.' }
  }

  const existing = current ?? {}
  if (!isJsonInputMultiDocument(existing) && uploads.length === 1) {
    return { ok: true, data: buildJsonInputNodeData(uploads, existing) }
  }

  let baseDocs: JsonInputDocument[]
  if (isJsonInputMultiDocument(existing)) {
    baseDocs = getJsonInputDocumentList(existing)
  } else if (flatHasUserContent(existing)) {
    baseDocs = [
      {
        ...articleFieldsFromNodeData(existing),
        text:
          typeof existing.text === 'string' ? existing.text : '',
        [JSON_INPUT_SOURCE_FILE_KEY]: 'Current content.json',
      },
    ]
  } else {
    baseDocs = []
  }

  const merged = [...baseDocs, ...uploads]
  if (merged.length > JSON_INPUT_MAX_DOCUMENTS) {
    return {
      ok: false,
      error: `You can add up to ${JSON_INPUT_MAX_DOCUMENTS} files at a time.`,
    }
  }
  return { ok: true, data: buildJsonInputNodeData(merged, existing) }
}
