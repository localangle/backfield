import { type S3InputSource, s3InputSourceFromGraphSpec } from '@/lib/s3InputSource'

/** Key on ``agate_run.result_json`` where the worker pins the flow spec at run start. */
export const GRAPH_SPEC_JSON_KEY = 'graph_spec_json'

export type GraphSpecLike = {
  nodes?: Array<{ type: string; params?: Record<string, unknown> }>
}

export function graphSpecSnapshotJsonFromRunResult(
  runResult: Record<string, unknown> | null | undefined,
): string | null {
  const raw = runResult?.[GRAPH_SPEC_JSON_KEY]
  return typeof raw === 'string' && raw.trim() ? raw : null
}

export function graphSpecSnapshotJsonFromRun(run: {
  graph_spec_snapshot_json?: string | null
  node_outputs?: Record<string, unknown> | null
}): string | null {
  if (run.graph_spec_snapshot_json?.trim()) {
    return run.graph_spec_snapshot_json
  }
  return graphSpecSnapshotJsonFromRunResult(run.node_outputs ?? null)
}

export function parseGraphSpecFromJson(json: string): GraphSpecLike | null {
  try {
    const parsed = JSON.parse(json) as unknown
    if (!parsed || typeof parsed !== 'object') return null
    const nodes = (parsed as GraphSpecLike).nodes
    if (!Array.isArray(nodes)) return null
    return parsed as GraphSpecLike
  } catch {
    return null
  }
}

/** Prefer the pinned run snapshot; fall back to the live saved flow spec. */
export function resolveRunGraphSpecForDisplay(
  snapshotJson: string | null,
  liveSpec: GraphSpecLike | undefined,
): { spec: GraphSpecLike | null; usedSnapshot: boolean } {
  if (snapshotJson) {
    const snapshotSpec = parseGraphSpecFromJson(snapshotJson)
    if (snapshotSpec) {
      return { spec: snapshotSpec, usedSnapshot: true }
    }
  }
  return { spec: liveSpec ?? null, usedSnapshot: false }
}

export function graphSpecJsonsEquivalent(aJson: string, bJson: string): boolean {
  try {
    const a = JSON.parse(aJson) as unknown
    const b = JSON.parse(bJson) as unknown
    return JSON.stringify(a) === JSON.stringify(b)
  } catch {
    return aJson.trim() === bJson.trim()
  }
}

export function flowChangedSinceRun(
  snapshotJson: string | null,
  liveSpecJson: string | null | undefined,
  apiFlag: boolean | null | undefined,
): boolean | null {
  if (apiFlag === true || apiFlag === false) {
    return apiFlag
  }
  if (!snapshotJson || !liveSpecJson?.trim()) {
    return null
  }
  return !graphSpecJsonsEquivalent(snapshotJson, liveSpecJson)
}

export function s3InputSourceForRun(
  snapshotJson: string | null,
  liveSpec: GraphSpecLike | undefined,
): { source: S3InputSource | null; usedSnapshot: boolean } {
  const { spec, usedSnapshot } = resolveRunGraphSpecForDisplay(snapshotJson, liveSpec)
  return {
    source: s3InputSourceFromGraphSpec(spec ?? undefined),
    usedSnapshot,
  }
}
