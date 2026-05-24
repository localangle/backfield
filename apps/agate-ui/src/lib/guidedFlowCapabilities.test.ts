import { describe, expect, it } from 'vitest'
import { getGuidedFlowCapabilities } from './guidedFlowCapabilities'

describe('getGuidedFlowCapabilities', () => {
  it('disables scaffold editing affordances when readOnly is true', () => {
    expect(getGuidedFlowCapabilities({ readOnly: true })).toEqual({
      allowAddNodes: false,
      allowEdgeInsert: false,
      allowDelete: false,
      allowBookendEdit: false,
      allowTidyLayout: false,
    })
  })

  it('enables scaffold editing affordances when readOnly is false', () => {
    expect(getGuidedFlowCapabilities({ readOnly: false })).toEqual({
      allowAddNodes: true,
      allowEdgeInsert: true,
      allowDelete: true,
      allowBookendEdit: true,
      allowTidyLayout: true,
    })
  })

  it('enables editing when editMode is true even if readOnly is omitted', () => {
    expect(getGuidedFlowCapabilities({ editMode: true })).toEqual({
      allowAddNodes: true,
      allowEdgeInsert: true,
      allowDelete: true,
      allowBookendEdit: true,
      allowTidyLayout: true,
    })
  })
})
