/** User-facing helpers for connection evidence on Stylebook edges. */

export interface ConnectionCreationEvidenceView {
  confidencePercent: number | null
  quote: string
  showReason: boolean
  reason: string
  sourceLabel: string
  currentnessLabel: string | null
}

export interface ConnectionStatusMetaRow {
  label: string
  value: string
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

export function formatConnectionDate(value: string | null | undefined): string | null {
  if (!value) return null
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  })
}

function connectionSourceLabel(conn: {
  evidence?: ReadonlyArray<object | null | undefined> | null
  evidence_json?: Record<string, unknown> | null
}): string | null {
  const evidence = bestEvidenceRecord(conn)
  if (!evidence) return null
  const raw = typeof evidence.source === "string" ? evidence.source : null
  if (!raw?.trim()) return null
  return sourceLabel(raw)
}

function evidenceObservedAt(conn: {
  evidence?: ReadonlyArray<object | null | undefined> | null
  evidence_json?: Record<string, unknown> | null
}): string | null {
  const evidence = bestEvidenceRecord(conn)
  if (!evidence) return null
  const raw = evidence.observed_at
  return typeof raw === "string" ? raw : null
}

/** Compact status rows for connection detail / list panels. */
export function formatConnectionStatusMeta(conn: {
  closed_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  temporal_kind?: "static" | "dynamic" | null
  currentness?: "current" | "former" | "unknown" | null
  currentness_as_of?: string | null
  evidence?: ReadonlyArray<object | null | undefined> | null
  evidence_json?: Record<string, unknown> | null
}): ConnectionStatusMetaRow[] {
  const rows: ConnectionStatusMetaRow[] = [
    { label: "Status", value: conn.closed_at ? "Closed" : "Open" },
  ]
  if (conn.temporal_kind === "static") {
    rows.push({ label: "Timing", value: "Enduring relationship" })
  } else if (conn.temporal_kind === "dynamic") {
    const asOf = formatConnectionDate(conn.currentness_as_of)
    if (conn.currentness === "current") {
      rows.push({
        label: "Currentness",
        value: asOf ? `Reported current as of ${asOf}` : "Reported current",
      })
    } else if (conn.currentness === "former") {
      rows.push({
        label: "Currentness",
        value: asOf ? `Reported former as of ${asOf}` : "Reported former",
      })
    } else {
      rows.push({ label: "Currentness", value: "Current status unknown" })
    }
  }
  const source = connectionSourceLabel(conn)
  if (source) {
    rows.push({ label: "Source", value: source })
  }
  const added = formatConnectionDate(conn.created_at)
  if (added) {
    rows.push({ label: "Added", value: added })
  }
  const closed = formatConnectionDate(conn.closed_at)
  if (closed) {
    rows.push({ label: "Closed", value: closed })
  }
  const observed = formatConnectionDate(evidenceObservedAt(conn))
  if (observed && observed !== added) {
    rows.push({ label: "Seen in coverage", value: observed })
  }
  return rows
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
  const assertedCurrentness =
    typeof row.asserted_currentness === "string" ? row.asserted_currentness : "unspecified"
  const currentnessLabel =
    assertedCurrentness === "current"
      ? "Reported current"
      : assertedCurrentness === "former"
        ? "Reported former"
        : null
  const displayQuote = quote || description
  if (!displayQuote && !reason && !currentnessLabel) {
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
    currentnessLabel,
  }
}

export function bestEvidenceRecord(conn: {
  evidence?: ReadonlyArray<object | null | undefined> | null
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
