/**
 * Presentation helpers for curated AI preset lists (`GET …/ai-models/curated-options`).
 *
 * Source of truth for *which* models exist stays in Core API `CURATED_TEMPLATES`. Each option
 * includes `provider` (e.g. `openai`, `anthropic`); we only group and label for the UI. New
 * templates with a `provider` slug appear under the right section automatically once the API
 * lists them. To change section order or display names, adjust
 * `CURATED_PROVIDER_SECTION_ORDER` and `curatedProviderSectionTitle` below.
 */

import type { CuratedAiModelOption } from '@/lib/core-api'

/** Section order in the Preset dropdown (providers not listed sort after these, A–Z). */
export const CURATED_PROVIDER_SECTION_ORDER = [
  'openai',
  'anthropic',
  'gemini',
  'openrouter',
  'mistral',
  'google',
  'meta-llama',
  'xai',
  'moonshot',
  'cohere',
  'azure',
] as const

export function curatedProviderSectionTitle(providerKey: string): string {
  const k = providerKey.toLowerCase()
  if (k === 'openai') return 'OpenAI'
  if (k === 'anthropic') return 'Anthropic'
  if (k === 'gemini') return 'Google Gemini'
  if (k === 'google') return 'Google'
  if (k === 'openrouter') return 'OpenRouter'
  if (k === 'meta-llama') return 'Meta Llama'
  if (k === 'mistral') return 'Mistral'
  if (k === 'xai') return 'xAI'
  if (k === 'moonshot') return 'Moonshot / Kimi'
  if (k === 'cohere') return 'Cohere'
  if (k === 'azure') return 'Azure OpenAI'
  const raw = providerKey.trim()
  return raw ? raw.charAt(0).toUpperCase() + raw.slice(1) : 'Other'
}

export type CuratedPresetSection = {
  providerKey: string
  providerLabel: string
  items: CuratedAiModelOption[]
}

/**
 * Group curated options by `provider` for a grouped Select.
 * Order within each section matches API list order (Core API dict insertion order), not A–Z by label.
 */
export function groupCuratedOptionsForPresetUi(options: CuratedAiModelOption[]): CuratedPresetSection[] {
  const byProvider = new Map<string, CuratedAiModelOption[]>()
  for (const opt of options) {
    const key = String(opt.provider || '').toLowerCase() || 'other'
    const list = byProvider.get(key) ?? []
    list.push(opt)
    byProvider.set(key, list)
  }

  const orderedKeys = new Set<string>()
  const keys: string[] = []
  for (const p of CURATED_PROVIDER_SECTION_ORDER) {
    if (byProvider.has(p)) {
      keys.push(p)
      orderedKeys.add(p)
    }
  }
  const rest = Array.from(byProvider.keys())
    .filter((k) => !orderedKeys.has(k))
    .sort((a, b) => a.localeCompare(b))
  keys.push(...rest)

  return keys.map((providerKey) => ({
    providerKey,
    providerLabel: curatedProviderSectionTitle(providerKey),
    items: byProvider.get(providerKey) ?? [],
  }))
}
