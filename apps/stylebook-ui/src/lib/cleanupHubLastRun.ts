/** Browser persistence for per-check cleanup hub runs (client-only). */

export interface CleanupCheckRunRecord {
  ranAtIso: string
  count: number
}

export type CleanupRunStore = Record<string, CleanupCheckRunRecord>

export interface CleanupHubPersistedState {
  records: CleanupRunStore
  lastRunByCheckId: Record<string, string>
}

export function cleanupLastRunStorageKey(stylebookSlug: string, project?: string): string {
  return `backfield:cleanup-last-run:${stylebookSlug}:${project ?? "__all__"}`
}

export function loadCleanupHubState(storageKey: string): CleanupHubPersistedState {
  try {
    const raw = localStorage.getItem(storageKey)
    if (!raw) {
      return { records: {}, lastRunByCheckId: {} }
    }
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== "object") {
      return { records: {}, lastRunByCheckId: {} }
    }

    const records: CleanupRunStore = {}
    const lastRunByCheckId: Record<string, string> = {}

    for (const [checkId, value] of Object.entries(parsed)) {
      if (typeof value === "string") {
        lastRunByCheckId[checkId] = value
        continue
      }
      if (!value || typeof value !== "object") continue
      const row = value as Partial<CleanupCheckRunRecord>
      if (typeof row.ranAtIso !== "string") continue
      lastRunByCheckId[checkId] = row.ranAtIso
      if (typeof row.count !== "number" || !Number.isFinite(row.count)) continue
      records[checkId] = {
        ranAtIso: row.ranAtIso,
        count: Math.max(0, Math.trunc(row.count)),
      }
    }

    return { records, lastRunByCheckId }
  } catch {
    return { records: {}, lastRunByCheckId: {} }
  }
}

export function saveCleanupCheckRun(
  storageKey: string,
  checkId: string,
  record: CleanupCheckRunRecord,
): CleanupHubPersistedState {
  const current = loadCleanupHubState(storageKey)
  const nextRecord: CleanupCheckRunRecord = {
    ranAtIso: record.ranAtIso,
    count: Math.max(0, Math.trunc(record.count)),
  }
  const records = { ...current.records, [checkId]: nextRecord }
  const lastRunByCheckId = { ...current.lastRunByCheckId, [checkId]: nextRecord.ranAtIso }

  const persisted: Record<string, CleanupCheckRunRecord | string> = {}
  for (const [id, ranAtIso] of Object.entries(lastRunByCheckId)) {
    const full = records[id]
    persisted[id] = full ?? ranAtIso
  }
  localStorage.setItem(storageKey, JSON.stringify(persisted))

  return { records, lastRunByCheckId }
}

export function formatCleanupLastRun(ranAtIso: string | undefined): string {
  if (!ranAtIso) return "—"
  const date = new Date(ranAtIso)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleString()
}

export type CleanupCheckStaleness = "fresh" | "aging" | "stale" | "never"

/** Fresh < 2 days; aging 2–4 days; stale 5+ days or never run. */
export function cleanupCheckStaleness(ranAtIso: string | undefined): CleanupCheckStaleness {
  if (!ranAtIso) return "never"
  const date = new Date(ranAtIso)
  if (Number.isNaN(date.getTime())) return "never"
  const daysSinceRun = (Date.now() - date.getTime()) / (1000 * 60 * 60 * 24)
  if (daysSinceRun >= 5) return "stale"
  if (daysSinceRun >= 2) return "aging"
  return "fresh"
}

function cleanupDaysSinceRun(ranAtIso: string): number {
  const date = new Date(ranAtIso)
  if (Number.isNaN(date.getTime())) return Number.POSITIVE_INFINITY
  return Math.floor((Date.now() - date.getTime()) / (1000 * 60 * 60 * 24))
}

export function formatCleanupStalenessLabel(ranAtIso: string | undefined): string {
  if (!ranAtIso) return "Not run yet"
  const days = cleanupDaysSinceRun(ranAtIso)
  if (!Number.isFinite(days)) return "Not run yet"
  if (days === 0) return "Run today"
  if (days === 1) return "Run yesterday"
  return `Last run ${days} days ago`
}
