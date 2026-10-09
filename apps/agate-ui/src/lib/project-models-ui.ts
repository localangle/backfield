import type { ProjectEffectiveAiModelRow } from '@/lib/core-api'
import { normalizeModelKind } from '@/lib/ai-model-catalog-ui'

export type ProjectModelKindBucket = {
  enabled: ProjectEffectiveAiModelRow[]
  disabled: ProjectEffectiveAiModelRow[]
}

export type PartitionedProjectModels = {
  generative: ProjectModelKindBucket
  embedding: ProjectModelKindBucket
  decision: ProjectModelKindBucket
}

/** Split active catalog rows by model kind and project availability. */
export function partitionProjectModelsByKind(
  rows: ProjectEffectiveAiModelRow[],
): PartitionedProjectModels {
  const out: PartitionedProjectModels = {
    generative: { enabled: [], disabled: [] },
    embedding: { enabled: [], disabled: [] },
    decision: { enabled: [], disabled: [] },
  }
  for (const row of rows) {
    if (row.status !== 'active') continue
    const bucket = out[normalizeModelKind(row.model_kind)]
    if (row.project_enabled) bucket.enabled.push(row)
    else bucket.disabled.push(row)
  }
  const byName = (a: ProjectEffectiveAiModelRow, b: ProjectEffectiveAiModelRow) =>
    a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
  for (const bucket of [out.generative, out.decision, out.embedding]) {
    bucket.enabled.sort(byName)
    bucket.disabled.sort(byName)
  }
  return out
}
