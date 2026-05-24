export type GuidedFlowCapabilities = {
  allowAddNodes: boolean
  allowEdgeInsert: boolean
  allowDelete: boolean
  allowBookendEdit: boolean
  allowTidyLayout: boolean
}

/** Derive scaffold editing affordances from run/view vs edit mode. */
export function getGuidedFlowCapabilities(options: {
  readOnly?: boolean
  editMode?: boolean
}): GuidedFlowCapabilities {
  const canEdit = options.editMode === true || options.readOnly === false
  return {
    allowAddNodes: canEdit,
    allowEdgeInsert: canEdit,
    allowDelete: canEdit,
    allowBookendEdit: canEdit,
    allowTidyLayout: canEdit,
  }
}
