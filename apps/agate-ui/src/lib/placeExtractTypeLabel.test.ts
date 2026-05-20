import { describe, expect, it } from 'vitest'
import { placeExtractTypeLabel } from './placeExtractTypeLabel'

describe('placeExtractTypeLabel', () => {
  it('applies explicit overrides', () => {
    expect(placeExtractTypeLabel('intersection_road')).toBe('Intersection (Road)')
    expect(placeExtractTypeLabel('political_district')).toBe('Political district')
  })

  it('title-cases unknown slugs', () => {
    expect(placeExtractTypeLabel('city')).toBe('City')
    expect(placeExtractTypeLabel('natural')).toBe('Natural')
  })
})
