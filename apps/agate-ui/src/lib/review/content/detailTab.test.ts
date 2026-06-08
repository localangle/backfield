import { describe, expect, it } from 'vitest'
import {
  defaultProcessedItemDetailTab,
  parseProcessedItemDetailTab,
  processedItemDetailTabSearch,
  readProcessedItemTabFromLocation,
} from './detailTab'

describe('processedItemDetailTab', () => {
  it('defaults to info tab', () => {
    expect(defaultProcessedItemDetailTab(false)).toBe('info')
    expect(defaultProcessedItemDetailTab(true)).toBe('info')
  })

  it('parses valid tab ids and falls back', () => {
    expect(parseProcessedItemDetailTab('json', { synthetic: false })).toBe('json')
    expect(parseProcessedItemDetailTab('bogus', { synthetic: false })).toBe('info')
    expect(parseProcessedItemDetailTab(null, { synthetic: true })).toBe('info')
    expect(parseProcessedItemDetailTab('events', { synthetic: false })).toBe('info')
    expect(parseProcessedItemDetailTab('works', { synthetic: false })).toBe('info')
  })

  it('reads tab from query before hash', () => {
    const params = new URLSearchParams('tab=meta')
    expect(readProcessedItemTabFromLocation(params)).toBe('meta')
  })

  it('builds permalink search', () => {
    expect(processedItemDetailTabSearch('places')).toBe('?tab=places')
  })
})
