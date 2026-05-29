import type { ProjectAiModelOption } from '@/components/NodePanel'

/** Sentinel select value used to surface a persisted model that is no longer in the catalog. */
export const INVALID_AI_MODEL_SELECTION_VALUE = '__bf_model_invalid__'

export type UnifiedAiModelOption = {
  selectValue: string
  label: string
  providerModelId: string
  configId?: string
}

/** Project AI catalog rows to de-duplicated select options keyed by config id (or provider model id). */
export function catalogToSelectOptions(catalog: ProjectAiModelOption[]): UnifiedAiModelOption[] {
  const out: UnifiedAiModelOption[] = []
  const seen = new Set<string>()
  for (const row of catalog) {
    const sv = row.configId ?? row.providerModelId
    if (sv === '' || seen.has(sv)) continue
    seen.add(sv)
    out.push({
      selectValue: sv,
      label: row.label,
      providerModelId: row.providerModelId,
      configId: row.configId,
    })
  }
  return out
}

/** The two param keys a node panel uses to persist a single AI model choice. */
export type AiModelFieldKeys = {
  configIdKey: string
  modelKey: string
}

/** Resolve the select value for an AI model field: prefer the config id, else map the model id. */
export function resolvedAiModelSelectValue(
  params: Record<string, unknown>,
  catalog: ProjectAiModelOption[],
  keys: AiModelFieldKeys,
): string {
  const cfg = params[keys.configIdKey]
  if (typeof cfg === 'string' && cfg.trim() !== '') return cfg.trim()
  const model = String(params[keys.modelKey] ?? '')
  const hit = catalog.find((r) => r.providerModelId === model && r.configId)
  if (hit?.configId) return hit.configId
  return model.trim()
}

/** True when the node data carries an explicit AI model choice (config id or model id). */
export function hasExplicitAiModelChoice(
  data: Record<string, unknown>,
  keys: AiModelFieldKeys,
): boolean {
  const cfg = data[keys.configIdKey]
  if (typeof cfg === 'string' && cfg.trim() !== '') return true
  const model = data[keys.modelKey]
  return typeof model === 'string' && model.trim() !== ''
}

/** Prefer canonical ``stylebook_id``; legacy persisted ``stylebookId`` is still read once. */
export function resolvedStylebookId(data: Record<string, unknown> | undefined): number | null {
  const d = data || {}
  const snake = d.stylebook_id
  const camel = d.stylebookId
  const raw = snake !== undefined && snake !== null ? snake : camel
  if (raw === null || raw === undefined || raw === '') return null
  const n = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(n) ? n : null
}
