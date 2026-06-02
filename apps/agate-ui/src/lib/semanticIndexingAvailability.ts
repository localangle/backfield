import {
  normalizeModelKind,
  SEMANTIC_EMBEDDING_DEFAULT_ROLE,
} from '@/lib/ai-model-catalog-ui'
import {
  fetchProjectAiModelDefaults,
  fetchProjectEffectiveAiModels,
  fetchProjectSemanticIndexingConfigured,
} from '@/lib/core-api'

/** Client-side check when Core API is older than the dedicated endpoint. */
async function inferSemanticIndexingConfiguredFromCatalog(
  projectId: number,
): Promise<boolean> {
  const [models, defaults] = await Promise.all([
    fetchProjectEffectiveAiModels(projectId, ['embedding']),
    fetchProjectAiModelDefaults(projectId),
  ])
  const enabled = models.filter(
    (row) => row.project_enabled && normalizeModelKind(row.model_kind) === 'embedding',
  )
  if (enabled.length === 1) {
    return true
  }
  const semanticDefault = defaults.find((d) => d.role === SEMANTIC_EMBEDDING_DEFAULT_ROLE)
  if (semanticDefault) {
    return enabled.some((row) => row.id === semanticDefault.model_config_id)
  }
  return false
}

/** Whether Backfield Output semantic indexing can run for this project. */
export async function isProjectSemanticIndexingConfigured(
  projectId: number,
): Promise<boolean> {
  try {
    const { configured } = await fetchProjectSemanticIndexingConfigured(projectId)
    return configured
  } catch {
    return inferSemanticIndexingConfiguredFromCatalog(projectId)
  }
}
