import { describe, expect, it } from 'vitest'
import {
  defaultProcessedItemDetailTab,
  parseProcessedItemDetailTab,
  processedItemDetailTabSearch,
  readProcessedItemTabFromLocation,
} from './processedItemDetailTab'

describe('processedItemDetailTab', () => {
  it('defaults by synthetic flag', () => {
    expect(defaultProcessedItemDetailTab(false)).toBe('places')
    expect(defaultProcessedItemDetailTab(true)).toBe('info')
  })

  it('parses valid tab ids and falls back', () => {
    expect(parseProcessedItemDetailTab('json', { synthetic: false })).toBe('json')
    expect(parseProcessedItemDetailTab('bogus', { synthetic: false })).toBe('places')
    expect(parseProcessedItemDetailTab(null, { synthetic: true })).toBe('info')
  })

  it('reads tab from query before hash', () => {
    const params = new URLSearchParams('tab=meta')
    expect(readProcessedItemTabFromLocation(params)).toBe('meta')
  })

  it('builds permalink search', () => {
    expect(processedItemDetailTabSearch('places')).toBe('?tab=places')
  })
})
