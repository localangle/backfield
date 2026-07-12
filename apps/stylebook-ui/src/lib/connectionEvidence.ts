/** User-facing helpers for automatic connection evidence on Stylebook edges. */

export interface ConnectionCreationEvidenceView {
  confidencePercent: number | null
  quote: string
  showReason: boolean
  reason: string
}

const MATCH_BASIS_PATTERN = /match_basis\s*=\s*[\w-]+/gi

/** Strip internal auto-connection metadata from user-facing copy. */
export function sanitizeConnectionDisplayText(text: string): string {
  return text.replace(MATCH_BASIS_PATTERN, "").replace(/\s+/g, " ").trim()
}

export function isInternalConnectionMetadata(text: string): boolean {
  const trimmed = text.trim()
  if (!trimmed) {
    return true
  }
  return /^match_basis\s*=\s*[\w-]+$/i.test(trimmed)
}

export function formatConnectionSummaryLabel(conn: {
  description?: string | null
  nature?: string | null
}): string {
  const description = sanitizeConnectionDisplayText(conn.description?.trim() ?? "")
  if (description && !isInternalConnectionMetadata(description)) {
    return description
  }
  const nature = conn.nature?.trim()
  if (nature) {
    return nature.replace(/_/g, " ")
  }
  return "Connection"
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
  const reason = sanitizeConnectionDisplayText(
    typeof row.reason === 'string' ? row.reason.trim() : '',
  )
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
