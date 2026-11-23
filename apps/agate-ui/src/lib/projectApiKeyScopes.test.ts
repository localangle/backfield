import { describe, expect, it } from 'vitest'
import {
  defaultCreateScopeSelection,
  normalizeScopeSelectionForType,
  scopesForCreateRequest,
  scopesForRotation,
} from './projectApiKeyScopes'

describe('projectApiKeyScopes', () => {
  it('defaults to read-only', () => {
    expect(scopesForCreateRequest('user', defaultCreateScopeSelection())).toBeUndefined()
    expect(scopesForCreateRequest('service', defaultCreateScopeSelection())).toBeUndefined()
  })

  it('requests runs:trigger only for service keys', () => {
    const withRuns = new Set(['read', 'runs:trigger'] as const)
    expect(scopesForCreateRequest('service', withRuns)).toEqual(['runs:trigger'])
    expect(scopesForCreateRequest('user', withRuns)).toBeUndefined()
  })

  it('strips runs:trigger from user key selection', () => {
    const selected = new Set(['read', 'runs:trigger'] as const)
    expect(normalizeScopeSelectionForType('user', selected)).toEqual(new Set(['read']))
    expect(normalizeScopeSelectionForType('service', selected)).toEqual(selected)
  })

  it('lets any key read for cleanup but only service keys make cleanup changes', () => {
    const selected = new Set(['read', 'cleanup:read', 'cleanup:apply'] as const)
    expect(scopesForCreateRequest('user', selected)).toEqual(['cleanup:read'])
    expect(normalizeScopeSelectionForType('user', selected)).toEqual(
      new Set(['read', 'cleanup:read']),
    )
    expect(scopesForCreateRequest('service', selected)).toEqual(['cleanup:read', 'cleanup:apply'])
  })

  it('selecting cleanup changes also selects cleanup reading', () => {
    const selected = new Set(['read', 'cleanup:apply'] as const)
    expect(normalizeScopeSelectionForType('service', selected)).toEqual(
      new Set(['read', 'cleanup:read', 'cleanup:apply']),
    )
  })

  it('keeps every granted scope when rotating a key', () => {
    const granted = ['read', 'runs:trigger', 'cleanup:read', 'cleanup:apply']
    expect(scopesForRotation('service', granted)).toEqual([
      'runs:trigger',
      'cleanup:read',
      'cleanup:apply',
    ])
    expect(scopesForRotation('user', ['read', 'cleanup:read'])).toEqual(['cleanup:read'])
    expect(scopesForRotation('user', ['read'])).toBeUndefined()
  })
})
