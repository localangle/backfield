import { createContext, useContext } from 'react'

export type GuidedFlowCanvasUi = {
  selectedNodeId: string | null
  enteringNodeIds: ReadonlySet<string>
}

const defaultUi: GuidedFlowCanvasUi = {
  selectedNodeId: null,
  enteringNodeIds: new Set(),
}

export const GuidedFlowCanvasUiContext = createContext<GuidedFlowCanvasUi>(defaultUi)

export function useGuidedFlowCanvasUi(): GuidedFlowCanvasUi {
  return useContext(GuidedFlowCanvasUiContext)
}
