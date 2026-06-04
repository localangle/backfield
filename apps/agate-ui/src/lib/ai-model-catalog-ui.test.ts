import { describe, expect, it } from 'vitest'
import {
  buildCustomCreateBody,
  buildPresetCreateBody,
  EMBEDDING_CURATED_PRESET_IDS,
  filterCuratedOptionsByKind,
  inferCuratedOptionKind,
  modelKindLabel,
  normalizeGenerativeCapabilities,
  resolveCapabilitiesForKind,
  resolvePresetCapabilities,
} from '@/lib/ai-model-catalog-ui'
import type { CuratedAiModelOption } from '@/lib/core-api'

const generativePreset: CuratedAiModelOption = {
  curated_id: 'openai:gpt-5-nano',
  provider: 'openai',
  provider_model_id: 'gpt-5-nano',
  label: 'GPT-5 Nano',
  model_kind: 'generative',
  capabilities: ['text', 'json'],
}

const embeddingPreset: CuratedAiModelOption = {
  curated_id: 'openai:text-embedding-3-small',
  provider: 'openai',
  provider_model_id: 'text-embedding-3-small',
  label: 'text-embedding-3-small',
  model_kind: 'embedding',
  capabilities: ['embedding'],
}

describe('filterCuratedOptionsByKind', () => {
  it('splits generative and embedding presets', () => {
    const all = [generativePreset, embeddingPreset]
    expect(filterCuratedOptionsByKind(all, 'generative')).toEqual([generativePreset])
    expect(filterCuratedOptionsByKind(all, 'embedding')).toEqual([embeddingPreset])
  })
})

describe('resolveCapabilitiesForKind', () => {
  it('locks embedding to the embedding capability', () => {
    expect(resolveCapabilitiesForKind('embedding', new Set(['text']))).toEqual(['embedding'])
  })

  it('keeps generative capability selection', () => {
    expect(resolveCapabilitiesForKind('generative', new Set(['text', 'vision']))).toEqual([
      'text',
      'vision',
    ])
  })
})

describe('resolvePresetCapabilities', () => {
  it('uses embedding capability for embedding presets', () => {
    expect(resolvePresetCapabilities(embeddingPreset)).toEqual(['embedding'])
  })

  it('filters generative preset capabilities to known keys', () => {
    expect(resolvePresetCapabilities(generativePreset)).toEqual(['text', 'json'])
  })
})

describe('buildPresetCreateBody', () => {
  it('includes model_kind for embedding presets', () => {
    const body = buildPresetCreateBody({
      curatedId: embeddingPreset.curated_id,
      option: embeddingPreset,
      integrationSecretId: 42,
      currency: 'USD',
    })
    expect(body.model_kind).toBe('embedding')
    expect(body.capabilities).toEqual(['embedding'])
    expect(body.curated_id).toBe('openai:text-embedding-3-small')
  })

  it('omits model_kind for generative presets', () => {
    const body = buildPresetCreateBody({
      curatedId: generativePreset.curated_id,
      option: generativePreset,
      name: 'Fast',
      integrationSecretId: 7,
      currency: 'USD',
    })
    expect(body.model_kind).toBeUndefined()
    expect(body.capabilities).toEqual(['text', 'json'])
  })
})

describe('buildCustomCreateBody', () => {
  it('builds a custom embedding row', () => {
    const body = buildCustomCreateBody({
      kind: 'embedding',
      name: 'Custom embed',
      litellmModel: 'openai/text-embedding-3-large',
      integrationSecretId: 3,
      selectedGenerativeCaps: new Set(['text']),
      currency: 'EUR',
    })
    expect(body).toMatchObject({
      model_kind: 'embedding',
      capabilities: ['embedding'],
      litellm_model: 'openai/text-embedding-3-large',
      currency: 'EUR',
    })
  })

  it('builds a custom generative row from selected caps', () => {
    const body = buildCustomCreateBody({
      kind: 'generative',
      name: 'Custom chat',
      litellmModel: 'together_ai/meta-llama/Llama-3-70b-chat-hf',
      integrationSecretId: 3,
      selectedGenerativeCaps: new Set(['text']),
      currency: 'USD',
    })
    expect(body.model_kind).toBe('generative')
    expect(body.capabilities).toEqual(['text'])
  })
})

describe('normalizeGenerativeCapabilities', () => {
  it('drops embedding from generative selections', () => {
    expect(normalizeGenerativeCapabilities(new Set(['text', 'embedding']))).toEqual(['text'])
  })
})

describe('inferCuratedOptionKind', () => {
  it('recognizes known embedding preset ids even without model_kind', () => {
    const withoutKind: CuratedAiModelOption = {
      ...embeddingPreset,
      model_kind: undefined,
      capabilities: [],
    }
    expect(inferCuratedOptionKind(withoutKind)).toBe('embedding')
  })

  it('lists the OpenAI embedding presets', () => {
    expect(EMBEDDING_CURATED_PRESET_IDS).toEqual([
      'openai:text-embedding-3-small',
      'openai:text-embedding-3-large',
    ])
  })
})

describe('modelKindLabel', () => {
  it('uses product-facing labels', () => {
    expect(modelKindLabel('generative')).toBe('Generative')
    expect(modelKindLabel('embedding')).toBe('Embedding')
  })
})
