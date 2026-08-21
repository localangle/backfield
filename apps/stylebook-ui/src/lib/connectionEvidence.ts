/** User-facing helpers for connection evidence on Stylebook edges. */

export interface ConnectionCreationEvidenceView {
  confidencePercent: number | null
  quote: string
  showReason: boolean
  reason: string
  sourceLabel: string
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
  return Boolean(evidence && typeof evidence === "object" && Object.keys(evidence).length > 0)
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

function sourceLabel(source: string | null | undefined): string {
  const value = (source || "").trim().toLowerCase()
  if (value === "manual" || value === "legacy_manual") return "Manual"
  if (value.includes("auto") || value === "dboutput_auto_connections") return "Automatic"
  if (value) return "Saved"
  return "Saved"
}

export function formatConnectionEvidence(
  evidence: Record<string, unknown> | null | undefined,
): ConnectionCreationEvidenceView | null {
  if (!hasConnectionEvidence(evidence)) {
    return null
  }
  const row = evidence as Record<string, unknown>
  const quote = typeof row.quote === "string" ? row.quote.trim() : ""
  const description =
    typeof row.description === "string" ? row.description.trim() : ""
  const reason = sanitizeConnectionDisplayText(
    typeof row.reason === "string" ? row.reason.trim() : "",
  )
  const displayQuote = quote || description
  if (!displayQuote && !reason) {
    return null
  }
  const confidenceRaw = row.confidence
  let confidencePercent: number | null = null
  if (typeof confidenceRaw === "number" && !Number.isNaN(confidenceRaw)) {
    confidencePercent = Math.round(confidenceRaw * 100)
  }
  const resolvedReason = reason || displayQuote
  return {
    confidencePercent,
    quote: displayQuote,
    showReason: shouldShowEvidenceReason(displayQuote, resolvedReason),
    reason: resolvedReason,
    sourceLabel: sourceLabel(typeof row.source === "string" ? row.source : null),
  }
}

export function bestEvidenceRecord(conn: {
  evidence?: Array<Record<string, unknown> | null | undefined> | null
  evidence_json?: Record<string, unknown> | null
}): Record<string, unknown> | null {
  const rows = Array.isArray(conn.evidence) ? conn.evidence : []
  for (const row of rows) {
    if (row && typeof row === "object") {
      return row as Record<string, unknown>
    }
  }
  if (conn.evidence_json && typeof conn.evidence_json === "object") {
    return conn.evidence_json
  }
  return null
}
