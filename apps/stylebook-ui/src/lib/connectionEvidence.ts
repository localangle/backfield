/** User-facing helpers for automatic connection evidence on Stylebook edges. */

export interface ConnectionCreationEvidenceView {
  sourceLabel: string
  confidenceLabel: string
  quote: string
  reason: string
}

const AUTO_SOURCE_LABEL = 'Added automatically while processing a story'

export function hasConnectionEvidence(
  evidence: Record<string, unknown> | null | undefined,
): boolean {
  return Boolean(evidence && typeof evidence === 'object' && Object.keys(evidence).length > 0)
}

export function formatConnectionEvidence(
  evidence: Record<string, unknown> | null | undefined,
): ConnectionCreationEvidenceView | null {
  if (!hasConnectionEvidence(evidence)) {
    return null
  }
  const row = evidence as Record<string, unknown>
  const quote = typeof row.quote === 'string' ? row.quote.trim() : ''
  const reason = typeof row.reason === 'string' ? row.reason.trim() : ''
  if (!quote && !reason) {
    return null
  }
  const sourceRaw = row.source
  const sourceLabel =
    typeof sourceRaw === 'string' && sourceRaw.trim() ? AUTO_SOURCE_LABEL : AUTO_SOURCE_LABEL
  const confidenceRaw = row.confidence
  let confidenceLabel = ''
  if (typeof confidenceRaw === 'number' && !Number.isNaN(confidenceRaw)) {
    confidenceLabel = `${Math.round(confidenceRaw * 100)}% confidence`
  }
  return {
    sourceLabel,
    confidenceLabel,
    quote,
    reason: reason || quote,
  }
}
