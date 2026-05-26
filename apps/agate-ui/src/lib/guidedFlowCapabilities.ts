export type GuidedFlowCapabilities = {
  allowAddNodes: boolean
  allowDelete: boolean
  allowBookendEdit: boolean
  allowNodeDrag: boolean
}

/** Derive scaffold editing affordances from run/view vs edit mode. */
export function getGuidedFlowCapabilities(options: {
  readOnly?: boolean
  editMode?: boolean
}): GuidedFlowCapabilities {
  const canEdit = options.editMode === true || options.readOnly === false
  return {
    allowAddNodes: canEdit,
    allowDelete: canEdit,
    allowBookendEdit: canEdit,
    allowNodeDrag: canEdit,
  }
}
