/**
 * Organization AI model catalog helpers for Settings → AI models.
 * Core API owns preset lists; this module handles generative vs similarity-search UX.
 */

import type { AiModelConfigCreateInput, CuratedAiModelOption } from '@/lib/core-api'

export type AiModelKind = 'generative' | 'embedding' | 'decision'

export const DECISION_CAPABILITY = 'decision'

export const GENERATIVE_CAPABILITY_KEYS = ['text', 'json', 'vision'] as const
export const EMBEDDING_CAPABILITY = 'embedding'

/** Core API / worker role for semantic document and query embeddings. */
export const SEMANTIC_EMBEDDING_DEFAULT_ROLE = 'semantic.embedding'

/** Core API role for the project default generative model (HyDE, headless LLM uses). */
export const GENERATIVE_DEFAULT_ROLE = 'generative.default'

/** Known embedding preset ids (API `model_kind` is authoritative). */
export const EMBEDDING_CURATED_PRESET_IDS = [
  'openai:text-embedding-3-small',
  'openai:text-embedding-3-large',
] as const

const EMBEDDING_CURATED_PRESET_ID_SET = new Set<string>(EMBEDDING_CURATED_PRESET_IDS)

export function normalizeModelKind(raw: string | undefined | null): AiModelKind {
  if (raw === 'embedding') return 'embedding'
  if (raw === 'decision') return 'decision'
  return 'generative'
}

/** User-facing label for catalog row kind badges and form copy. */
export function modelKindLabel(kind: AiModelKind): string {
  if (kind === 'embedding') return 'Embedding'
  if (kind === 'decision') return 'Decision'
  return 'Generative'
}

export function customModelPickerLead(kind: AiModelKind): string {
  if (kind === 'embedding') return 'Choose a provider embedding model from '
  if (kind === 'decision') return 'Choose a decision model from '
  return 'Choose any LiteLLM supported model from '
}

export function customModelRoutingPlaceholder(kind: AiModelKind): string {
  if (kind === 'embedding') return 'ex. openai/text-embedding-3-small'
  if (kind === 'decision') return 'ex. typesafe/jev-latest'
  return 'ex. azure_ai/claude-haiku-4-5'
}

export function inferCuratedOptionKind(option: CuratedAiModelOption): AiModelKind {
  if (option.model_kind === 'decision' || option.model_kind === 'embedding') {
    return option.model_kind
  }
  if (option.capabilities.includes(DECISION_CAPABILITY)) {
    return 'decision'
  }
  if (option.capabilities.includes(EMBEDDING_CAPABILITY)) {
    return 'embedding'
  }
  if (EMBEDDING_CURATED_PRESET_ID_SET.has(option.curated_id)) {
    return 'embedding'
  }
  return 'generative'
}

export function filterCuratedOptionsByKind(
  options: CuratedAiModelOption[],
  kind: AiModelKind,
): CuratedAiModelOption[] {
  return options.filter((o) => inferCuratedOptionKind(o) === kind)
}

export function normalizeGenerativeCapabilities(selected: Set<string>): string[] {
  return GENERATIVE_CAPABILITY_KEYS.filter((k) => selected.has(k))
}

export function resolveCapabilitiesForKind(
  kind: AiModelKind,
  selectedGenerativeCaps: Set<string>,
): string[] {
  if (kind === 'embedding') {
    return [EMBEDDING_CAPABILITY]
  }
  if (kind === 'decision') {
    return [DECISION_CAPABILITY]
  }
  return normalizeGenerativeCapabilities(selectedGenerativeCaps)
}

/** Capabilities sent on create for a curated preset (from API option, not checkbox state). */
export function resolvePresetCapabilities(option: CuratedAiModelOption | undefined): string[] {
  if (!option) return []
  const kind = inferCuratedOptionKind(option)
  if (kind === 'embedding') {
    return [EMBEDDING_CAPABILITY]
  }
  if (kind === 'decision') {
    return [DECISION_CAPABILITY]
  }
  return normalizeGenerativeCapabilities(new Set(option.capabilities))
}

export function buildPresetCreateBody(input: {
  curatedId: string
  option: CuratedAiModelOption | undefined
  name?: string
  integrationSecretId: number
  currency: string
  prices?: Pick<AiModelConfigCreateInput, 'input_token_price' | 'output_token_price'>
}): AiModelConfigCreateInput {
  const kind = input.option ? inferCuratedOptionKind(input.option) : 'generative'
  const caps = resolvePresetCapabilities(input.option)
  const body: AiModelConfigCreateInput = {
    curated_id: input.curatedId,
    name: input.name?.trim() || undefined,
    capabilities: caps,
    currency: input.currency,
    integration_secret_id: input.integrationSecretId,
    ...input.prices,
  }
  if (kind === 'embedding' || kind === 'decision') {
    body.model_kind = kind
  }
  return body
}

export function buildCustomCreateBody(input: {
  kind: AiModelKind
  name: string
  litellmModel: string
  integrationSecretId: number
  selectedGenerativeCaps: Set<string>
  currency: string
  prices?: Pick<AiModelConfigCreateInput, 'input_token_price' | 'output_token_price'>
}): AiModelConfigCreateInput {
  const caps = resolveCapabilitiesForKind(input.kind, input.selectedGenerativeCaps)
  return {
    name: input.name.trim(),
    litellm_model: input.litellmModel.trim(),
    integration_secret_id: input.integrationSecretId,
    model_kind: input.kind,
    capabilities: caps,
    currency: input.currency,
    ...input.prices,
  }
}

export function defaultGenerativeCaps(): Set<string> {
  return new Set(['text', 'json'])
}
