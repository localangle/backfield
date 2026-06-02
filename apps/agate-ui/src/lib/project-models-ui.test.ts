import { describe, expect, it } from 'vitest'
import { partitionProjectModelsByKind } from '@/lib/project-models-ui'
import type { ProjectEffectiveAiModelRow } from '@/lib/core-api'

function row(
  partial: Partial<ProjectEffectiveAiModelRow> & Pick<ProjectEffectiveAiModelRow, 'id' | 'name'>,
): ProjectEffectiveAiModelRow {
  return {
    provider: 'openai',
    provider_model_id: 'test',
    model_kind: 'generative',
    status: 'active',
    capabilities: ['text'],
    project_enabled: true,
    ...partial,
  }
}

describe('partitionProjectModelsByKind', () => {
  it('splits generative and embedding rows by availability', () => {
    const parts = partitionProjectModelsByKind([
      row({ id: 'g1', name: 'GPT', model_kind: 'generative', project_enabled: true }),
      row({
        id: 'e1',
        name: 'Embed',
        model_kind: 'embedding',
        capabilities: ['embedding'],
        project_enabled: false,
      }),
    ])
    expect(parts.generative.enabled.map((r) => r.id)).toEqual(['g1'])
    expect(parts.embedding.disabled.map((r) => r.id)).toEqual(['e1'])
    expect(parts.embedding.enabled).toEqual([])
  })
})
