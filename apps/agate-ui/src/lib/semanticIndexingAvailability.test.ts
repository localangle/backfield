import { describe, expect, it } from 'vitest'
import {
  semanticIndexingSelectDisabled,
  semanticIndexingUiShowsYes,
  shouldAutoClearSemanticIndexingEnabled,
} from './semanticIndexingAvailability'

describe('semanticIndexingAvailability helpers', () => {
  it('does not auto-clear while availability is still loading', () => {
    expect(shouldAutoClearSemanticIndexingEnabled(null, true)).toBe(false)
  })

  it('auto-clears when embedding is confirmed unavailable', () => {
    expect(shouldAutoClearSemanticIndexingEnabled(false, true)).toBe(true)
    expect(shouldAutoClearSemanticIndexingEnabled(false, false)).toBe(false)
  })

  it('shows saved Yes while availability is loading', () => {
    expect(semanticIndexingUiShowsYes(null, true)).toBe(true)
    expect(semanticIndexingUiShowsYes(false, true)).toBe(false)
    expect(semanticIndexingUiShowsYes(true, true)).toBe(true)
  })

  it('keeps select enabled while loading and disables when unavailable', () => {
    expect(semanticIndexingSelectDisabled(null, false)).toBe(false)
    expect(semanticIndexingSelectDisabled(false, false)).toBe(true)
    expect(semanticIndexingSelectDisabled(true, true)).toBe(true)
  })
})
