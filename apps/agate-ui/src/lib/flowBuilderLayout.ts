import { MarkerType, type Edge, type Node } from 'reactflow'

import { resolveEdgeHandles } from '@/lib/nodeCompatibility'

/** Fixed bookend positions for the guided builder preview (one column step apart). */
export const BOOKEND_INPUT_POSITION = { x: 80, y: 120 }
/** Matches {@link LAYOUT_X_STEP} in flowGraphModel — keep bookend preview spacing in sync. */
export const BOOKEND_LAYOUT_X_STEP = 232
export const BOOKEND_OUTPUT_POSITION = {
  x: BOOKEND_INPUT_POSITION.x + BOOKEND_LAYOUT_X_STEP,
  y: BOOKEND_INPUT_POSITION.y,
}

export function withBookendPositions(inputNode: Node | null, outputNode: Node | null): Node[] {
  const nodes: Node[] = []
  if (inputNode) {
    nodes.push({ ...inputNode, position: BOOKEND_INPUT_POSITION })
  }
  if (outputNode) {
    nodes.push({ ...outputNode, position: BOOKEND_OUTPUT_POSITION })
  }
  return nodes
}

/** Preview edge between bookends when the middle is still empty. */
export function bookendPreviewEdge(inputNode: Node, outputNode: Node): Edge {
  const handles =
    inputNode.type && outputNode.type
      ? resolveEdgeHandles(String(inputNode.type), String(outputNode.type))
      : null
  return {
    id: `${inputNode.id}-${outputNode.id}-preview`,
    source: inputNode.id,
    target: outputNode.id,
    sourceHandle: handles?.sourceHandle ?? null,
    targetHandle: handles?.targetHandle ?? null,
    type: 'smoothstep',
    animated: false,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: '#000000',
      width: 18,
      height: 18,
    },
    style: { stroke: '#000000', strokeWidth: 1 },
  }
}
