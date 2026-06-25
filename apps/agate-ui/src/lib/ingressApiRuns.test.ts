import { describe, expect, it } from 'vitest'
import { inferIngressPublicAlias, sanitizePublicAlias } from './ingressApiRuns'
import { paramsForGraphSave } from './flowValidation'

describe('sanitizePublicAlias', () => {
  it('slugifies labels with spaces and punctuation', () => {
    expect(sanitizePublicAlias('Text Input')).toBe('text_input')
    expect(sanitizePublicAlias('JSON Input!')).toBe('json_input')
  })

  it('falls back to input when slug is empty', () => {
    expect(sanitizePublicAlias('---')).toBe('input')
  })
})

describe('inferIngressPublicAlias', () => {
  it('uses node type label when no custom name is set', () => {
    expect(inferIngressPublicAlias('TextInput')).toBe('text_input')
    expect(inferIngressPublicAlias('JSONInput')).toBe('json_input')
    expect(inferIngressPublicAlias('S3Input')).toBe('s3_input')
  })

  it('prefers params.name over the type label', () => {
    expect(
      inferIngressPublicAlias('TextInput', { name: 'Breaking News Feed' }),
    ).toBe('breaking_news_feed')
  })
})

describe('paramsForGraphSave ingress API runs', () => {
  it('adds public_alias when public runs are enabled', () => {
    const params = paramsForGraphSave(
      { id: 'in', type: 'TextInput', data: { text: 'hello' } },
      { publicRunEnabled: true },
    )
    expect(params.public_alias).toBe('text_input')
  })

  it('removes public_alias when public runs are disabled', () => {
    const params = paramsForGraphSave(
      { id: 'in', type: 'TextInput', data: { text: 'hello', public_alias: 'legacy' } },
      { publicRunEnabled: false },
    )
    expect(params.public_alias).toBeUndefined()
  })
})
