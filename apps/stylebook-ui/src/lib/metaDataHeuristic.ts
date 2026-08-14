/**
 * Helpers for Stylebook typed canonical metadata (slug keys + scalar values).
 */

export type MetaValueType = "text" | "number" | "boolean"

const META_TYPE_PATTERN = /^[a-z0-9_]+$/

export function normalizeMetaTypeSlug(raw: string): string {
  return raw.trim().toLowerCase().replace(/-/g, "_").replace(/\s+/g, "_")
}

export function isValidMetaTypeSlug(raw: string): boolean {
  const slug = normalizeMetaTypeSlug(raw)
  return slug.length > 0 && META_TYPE_PATTERN.test(slug)
}

export function formatMetaValue(value: string | number | boolean): string {
  if (typeof value === "boolean") return value ? "True" : "False"
  return String(value)
}

export function parseMetaValueInput(
  valueType: MetaValueType,
  text: string,
): { ok: true; value: string | number | boolean } | { ok: false; error: string } {
  if (valueType === "text") {
    const trimmed = text.trim()
    if (!trimmed) return { ok: false, error: "Enter a value." }
    if (trimmed.includes(":")) {
      return { ok: false, error: "Text values cannot include a colon." }
    }
    return { ok: true, value: trimmed }
  }
  if (valueType === "boolean") {
    const t = text.trim().toLowerCase()
    if (t === "true") return { ok: true, value: true }
    if (t === "false") return { ok: true, value: false }
    return { ok: false, error: "Choose true or false." }
  }
  const trimmed = text.trim()
  if (!trimmed) return { ok: false, error: "Enter a number." }
  const n = Number(trimmed)
  if (!Number.isFinite(n)) return { ok: false, error: "Enter a valid number." }
  return { ok: true, value: n }
}
