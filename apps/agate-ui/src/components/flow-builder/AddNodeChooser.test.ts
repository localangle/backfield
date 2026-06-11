import { describe, expect, it } from 'vitest'

import type { CompatibleNodeEntry } from '@/lib/nodeCompatibility'
import { getNodeChooserBlurb, sortExtractChooserRows } from './AddNodeChooser'

function row(type: string, label: string): CompatibleNodeEntry & { rowKey: string } {
  return {
    type,
    label,
    description: '',
    category: 'extraction',
    enabled: true,
    reason: null,
    rowKey: type,
  }
}

describe('AddNodeChooser helpers', () => {
  it('uses product copy for known node types', () => {
    expect(getNodeChooserBlurb({ type: 'PlaceExtract', description: 'old' })).toBe(
      'Extract and standardize places',
    )
    expect(getNodeChooserBlurb({ type: 'EmbedImages', description: 'old' })).toBe(
      'Describe and semantically embed images',
    )
  })

  it('puts Custom Extract last in the Extract section', () => {
    const sorted = sortExtractChooserRows([
      row('CustomExtract', 'Custom Extract'),
      row('PlaceExtract', 'Place Extract'),
      row('PersonExtract', 'Person Extract'),
      row('OrganizationExtract', 'Organization Extract'),
    ])
    expect(sorted.map((entry) => entry.type)).toEqual([
      'OrganizationExtract',
      'PersonExtract',
      'PlaceExtract',
      'CustomExtract',
    ])
  })
})
