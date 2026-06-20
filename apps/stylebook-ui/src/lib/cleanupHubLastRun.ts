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
