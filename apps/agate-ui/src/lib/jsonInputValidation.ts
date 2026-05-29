/** Set on node data while the JSON editor content fails validation (not persisted on save). */
export const JSON_INPUT_INVALID_MARKER = '__jsonInputInvalid'

export function jsonInputInvalidNodeData(): Record<string, unknown> {
  return { [JSON_INPUT_INVALID_MARKER]: true }
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

/** Valid JSON Input node data: a JSON object with a string `text` field (may be empty). */
export function isValidJsonInputData(
  data: unknown,
): data is Record<string, unknown> & { text: string } {
  if (isJsonInputInvalidNodeData(data)) {
    return false
  }
  if (typeof data !== 'object' || data === null || Array.isArray(data)) {
    return false
  }
  if (!('text' in data)) {
    return false
  }
  return typeof (data as Record<string, unknown>).text === 'string'
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
