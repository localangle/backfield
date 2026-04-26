/**
 * Heuristics for Stylebook location meta `data_json`: treat plain objects whose
 * values are JSON scalars as "simple key / value" for a table UI; everything
 * else uses the raw JSON editor.
 */

export type ScalarJson = null | boolean | number | string

export function isScalarJson(value: unknown): value is ScalarJson {
  return value === null || typeof value === "string" || typeof value === "number" || typeof value === "boolean"
}

/** Non-null plain object with only scalar values (no nested objects/arrays). */
export function isFlatScalarRecord(data: unknown): data is Record<string, ScalarJson> {
  if (data === null || typeof data !== "object" || Array.isArray(data)) return false
  const o = data as Record<string, unknown>
  return Object.values(o).every(isScalarJson)
}

export type KeyValueRow = { id: string; key: string; valueStr: string }

function newRowId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID()
  }
  return `row-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

/** Build editable rows from a flat scalar map (stable key order). */
export function flatRecordToRows(data: Record<string, ScalarJson>): KeyValueRow[] {
  const keys = Object.keys(data).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }))
  if (keys.length === 0) {
    return [{ id: newRowId(), key: "", valueStr: "" }]
  }
  return keys.map((key) => ({
    id: newRowId(),
    key,
    valueStr: valueToCellString(data[key]),
  }))
}

export function valueToCellString(value: ScalarJson): string {
  if (value === null) return "null"
  if (typeof value === "string") return value
  return JSON.stringify(value)
}

/**
 * Parse a single table cell into a JSON scalar. Accepts JSON literals (`42`, `"x"`, `true`);
 * otherwise treats the trimmed string as a plain string (so typing `hello` works without quotes).
 */
export function parseScalarCell(text: string): { ok: true; value: ScalarJson } | { ok: false; error: string } {
  const t = text.trim()
  if (t === "") return { ok: true, value: "" }
  try {
    const v: unknown = JSON.parse(t)
    if (v !== null && typeof v === "object") {
      return {
        ok: false,
        error: "Objects and arrays belong in JSON mode; use a primitive here or switch editor.",
      }
    }
    return { ok: true, value: v as ScalarJson }
  } catch {
    return { ok: true, value: t }
  }
}

export function rowsToFlatRecord(
  rows: KeyValueRow[],
): { ok: true; data: Record<string, ScalarJson> } | { ok: false; error: string } {
  const out: Record<string, ScalarJson> = {}
  const seen = new Set<string>()

  for (const row of rows) {
    const k = row.key.trim()
    if (k === "" && row.valueStr.trim() === "") continue
    if (k === "") {
      return { ok: false, error: "Each row needs a key, or remove empty rows." }
    }
    if (seen.has(k)) {
      return { ok: false, error: `Duplicate key: "${k}"` }
    }
    seen.add(k)
    const parsed = parseScalarCell(row.valueStr)
    if (!parsed.ok) return { ok: false, error: parsed.error }
    out[k] = parsed.value
  }

  return { ok: true, data: out }
}

export function emptyKeyValueRows(): KeyValueRow[] {
  return [{ id: newRowId(), key: "", valueStr: "" }]
}

/** One blank row (use when appending to an existing table). */
export function newKeyValueRow(): KeyValueRow {
  return { id: newRowId(), key: "", valueStr: "" }
}
