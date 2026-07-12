/** Accent- and apostrophe-insensitive label matching (mirrors backend match_normalize). */

const UNICODE_APOSTROPHE_RE = /[\u2018\u2019\u02bc\u0060]/g

export function normalizeMatchText(value: string): string {
  return value
    .trim()
    .replace(UNICODE_APOSTROPHE_RE, "'")
    .toLowerCase()
    .replace(/\s+/g, " ")
}

export function matchFoldKey(value: string): string {
  const normalized = normalizeMatchText(value)
  if (!normalized) return ""
  return normalized.normalize("NFD").replace(/\p{M}/gu, "")
}
