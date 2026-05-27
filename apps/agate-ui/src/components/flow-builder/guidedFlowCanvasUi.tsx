import { createContext, useContext } from 'react'

export type GuidedFlowCanvasUi = {
  selectedNodeId: string | null
  enteringNodeIds: ReadonlySet<string>
  /** Direct node body clicks (React Flow onNodeClick is unreliable with custom shells). */
  onNodeActivate?: (nodeId: string) => void
}

const defaultUi: GuidedFlowCanvasUi = {
  selectedNodeId: null,
  enteringNodeIds: new Set(),
  onNodeActivate: undefined,
}

export const GuidedFlowCanvasUiContext = createContext<GuidedFlowCanvasUi>(defaultUi)

export function useGuidedFlowCanvasUi(): GuidedFlowCanvasUi {
  return useContext(GuidedFlowCanvasUiContext)
}
