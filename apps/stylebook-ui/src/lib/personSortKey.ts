/** Derive person list sort key from a display name (last token, or sole token). */
export function derivePersonSortKeyFromLabel(label: string): string {
  const normalize = (value: string) => value.trim().toLowerCase().replace(/\s+/g, " ")
  const trimmed = label.trim()
  if (!trimmed) return ""
  const parts = trimmed.split(/\s+/)
  if (parts.length >= 2) return normalize(parts[parts.length - 1]!)
  return normalize(parts[0]!)
}
