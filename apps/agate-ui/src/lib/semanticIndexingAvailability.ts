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

/** Auto-clear stored flag only when embedding is confirmed unavailable (not while loading). */
export function shouldAutoClearSemanticIndexingEnabled(
  configured: boolean | null,
  enabled: boolean,
): boolean {
  return configured === false && enabled
}

/** Yes/no display for the semantic indexing select (preserve saved Yes while availability loads). */
export function semanticIndexingUiShowsYes(
  configured: boolean | null,
  enabled: boolean,
): boolean {
  return enabled && configured !== false
}

/** Whether the semantic indexing select should be disabled. */
export function semanticIndexingSelectDisabled(
  configured: boolean | null,
  panelDisabled: boolean,
): boolean {
  return panelDisabled || configured === false
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
