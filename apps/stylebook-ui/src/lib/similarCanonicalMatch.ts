/**
 * Strict label matching for the canonical detail "similar records" notice.
 *
 * Deliberately much stricter than the create-flow nudge in
 * `candidateQueueSimilarity.ts`: an unsolicited banner must have near-zero
 * false positives, so we only treat labels as material duplicates when they
 * are the same name modulo qualifiers (leading "The", trailing
 * comma-separated qualifiers like state or country).
 */

function normalizeForDuplicateCompare(value: string): string {
  let normalized = value
    .trim()
    .toLowerCase()
    .replace(/[\u2010-\u2015]/g, "-") // unicode dashes → hyphen
    .replace(/\./g, "")
    .replace(/\s+/g, " ")
  if (normalized.startsWith("the ")) {
    normalized = normalized.slice(4)
  }
  return normalized
}

function commaSegments(value: string): string[] {
  return value
    .split(",")
    .map((segment) => segment.trim())
    .filter(Boolean)
}

/**
 * True when two labels name the same thing modulo qualifiers.
 *
 * Matches: "Kentucky" / "Kentucky, US"; "Chicago, IL" / "Chicago, IL, USA";
 * "The University of Chicago" / "University of Chicago".
 * Does not match: "Chicago, IL" / "O'Hare International Airport, Chicago, IL"
 * (different head) or "Springfield, IL" / "Springfield, MO" (same length,
 * different qualifiers).
 */
export function isMaterialDuplicateLabel(a: string, b: string): boolean {
  const normalizedA = normalizeForDuplicateCompare(a)
  const normalizedB = normalizeForDuplicateCompare(b)
  if (!normalizedA || !normalizedB) return false
  if (normalizedA === normalizedB) return true
  const segmentsA = commaSegments(normalizedA)
  const segmentsB = commaSegments(normalizedB)
  if (segmentsA.length === segmentsB.length) return false
  const [shorter, longer] =
    segmentsA.length < segmentsB.length ? [segmentsA, segmentsB] : [segmentsB, segmentsA]
  return shorter.every((segment, index) => segment === longer[index])
}

/** Core name used as the live-search query so both directions are found (e.g. "Kentucky, US" finds "Kentucky"). */
export function duplicateSearchQuery(label: string): string {
  const normalized = normalizeForDuplicateCompare(label)
  return commaSegments(normalized)[0] ?? ""
}
