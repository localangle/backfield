import type { ProjectEffectiveAiModelRow } from '@/lib/core-api'
import { normalizeModelKind } from '@/lib/ai-model-catalog-ui'

export type PartitionedProjectModels = {
  generative: {
    enabled: ProjectEffectiveAiModelRow[]
    disabled: ProjectEffectiveAiModelRow[]
  }
  embedding: {
    enabled: ProjectEffectiveAiModelRow[]
    disabled: ProjectEffectiveAiModelRow[]
  }
}

/** Split active catalog rows by model kind and project availability. */
export function partitionProjectModelsByKind(
  rows: ProjectEffectiveAiModelRow[],
): PartitionedProjectModels {
  const out: PartitionedProjectModels = {
    generative: { enabled: [], disabled: [] },
    embedding: { enabled: [], disabled: [] },
  }
  for (const row of rows) {
    if (row.status !== 'active') continue
    const bucket =
      normalizeModelKind(row.model_kind) === 'embedding' ? out.embedding : out.generative
    if (row.project_enabled) bucket.enabled.push(row)
    else bucket.disabled.push(row)
  }
  const byName = (a: ProjectEffectiveAiModelRow, b: ProjectEffectiveAiModelRow) =>
    a.name.localeCompare(b.name, undefined, { sensitivity: 'base' })
  for (const bucket of [out.generative, out.embedding]) {
    bucket.enabled.sort(byName)
    bucket.disabled.sort(byName)
  }
  return out
}
