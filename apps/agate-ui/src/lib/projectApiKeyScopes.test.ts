import { describe, expect, it } from 'vitest'
import {
  defaultCreateScopeSelection,
  normalizeScopeSelectionForType,
  scopesForCreateRequest,
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
})
