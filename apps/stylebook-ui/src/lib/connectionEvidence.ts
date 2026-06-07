/** User-facing helpers for automatic connection evidence on Stylebook edges. */

export interface ConnectionCreationEvidenceView {
  confidencePercent: number | null
  quote: string
  showReason: boolean
  reason: string
}

export function hasConnectionEvidence(
  evidence: Record<string, unknown> | null | undefined,
): boolean {
  return Boolean(evidence && typeof evidence === 'object' && Object.keys(evidence).length > 0)
}

export function shouldShowEvidenceReason(quote: string, reason: string): boolean {
  if (!reason.trim() || reason.trim() === quote.trim()) {
    return false
  }
  const q = quote.trim().toLowerCase()
  const r = reason.trim().toLowerCase()
  if (q && (r.includes(q) || q.includes(r))) {
    return false
  }
  if (/supports?\s+[\w_]+\s+relationship\.?$/i.test(reason.trim())) {
    return false
  }
  return reason.trim().length <= 160
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
  const confidenceRaw = row.confidence
  let confidencePercent: number | null = null
  if (typeof confidenceRaw === 'number' && !Number.isNaN(confidenceRaw)) {
    confidencePercent = Math.round(confidenceRaw * 100)
  }
  const resolvedReason = reason || quote
  return {
    confidencePercent,
    quote,
    showReason: shouldShowEvidenceReason(quote, resolvedReason),
    reason: resolvedReason,
  }
}
