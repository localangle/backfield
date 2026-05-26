import { describe, expect, it } from 'vitest'
import { getGuidedFlowCapabilities } from './guidedFlowCapabilities'

describe('getGuidedFlowCapabilities', () => {
  it('disables scaffold editing affordances when readOnly is true', () => {
    expect(getGuidedFlowCapabilities({ readOnly: true })).toEqual({
      allowAddNodes: false,
      allowDelete: false,
      allowBookendEdit: false,
      allowNodeDrag: false,
    })
  })

  it('enables scaffold editing affordances when readOnly is false', () => {
    expect(getGuidedFlowCapabilities({ readOnly: false })).toEqual({
      allowAddNodes: true,
      allowDelete: true,
      allowBookendEdit: true,
      allowNodeDrag: true,
    })
  })

  it('enables editing when editMode is true even if readOnly is omitted', () => {
    expect(getGuidedFlowCapabilities({ editMode: true })).toEqual({
      allowAddNodes: true,
      allowDelete: true,
      allowBookendEdit: true,
      allowNodeDrag: true,
    })
  })
})
