import { createContext, useContext, type MutableRefObject } from 'react'
import type { Node } from 'reactflow'
import type { AddNodeChooserAnchorRect } from '@/components/flow-builder/AddNodeChooser'

/**
 * Callbacks held in a ref so that callers can swap them on every render
 * without invalidating the canvas's stable nodeTypes map. React Flow remounts
 * every node when nodeTypes changes identity, which drops in-flight clicks and
 * makes the focus ring "pulse" on remount.
 */
export type GuidedFlowCanvasCallbacks = {
  onNodeClick?: (node: Node) => void
  onAddNodeClick?: (parentNodeId: string, anchorRect: AddNodeChooserAnchorRect) => void
  onAddEdgeClick?: (sourceNodeId: string, targetNodeId: string, anchorRect: AddNodeChooserAnchorRect) => void
  onDeleteNodeClick?: (nodeId: string) => void
  onSwapInputBookend?: () => void
  onSwapOutputBookend?: () => void
}

export type GuidedFlowCanvasUi = {
  selectedNodeId: string | null
  enteringNodeIds: ReadonlySet<string>
  invalidNodeIds: ReadonlySet<string>
  inputBookendId: string | null
  outputBookendId: string | null
  allowAddNodes: boolean
  allowBookendSwap: boolean
  allowDeleteNodes: boolean
  readOnly: boolean
  deletableNodeIds: ReadonlySet<string>
  callbacks: MutableRefObject<GuidedFlowCanvasCallbacks>
}

const emptyCallbacksRef: MutableRefObject<GuidedFlowCanvasCallbacks> = { current: {} }

const defaultUi: GuidedFlowCanvasUi = {
  selectedNodeId: null,
  enteringNodeIds: new Set(),
  invalidNodeIds: new Set(),
  inputBookendId: null,
  outputBookendId: null,
  allowAddNodes: false,
  allowBookendSwap: false,
  allowDeleteNodes: false,
  readOnly: false,
  deletableNodeIds: new Set(),
  callbacks: emptyCallbacksRef,
}

export const GuidedFlowCanvasUiContext = createContext<GuidedFlowCanvasUi>(defaultUi)

export function useGuidedFlowCanvasUi(): GuidedFlowCanvasUi {
  return useContext(GuidedFlowCanvasUiContext)
}
