import type { Edge, Node } from 'reactflow'

/** Fixed bookend positions for the guided builder (Issue 5 may refine layout). */
export const BOOKEND_INPUT_POSITION = { x: 80, y: 120 }
export const BOOKEND_OUTPUT_POSITION = { x: 520, y: 120 }

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
  return {
    id: `${inputNode.id}-${outputNode.id}-preview`,
    source: inputNode.id,
    target: outputNode.id,
    animated: false,
    style: { strokeDasharray: '6 4', stroke: 'hsl(var(--muted-foreground))', opacity: 0.5 },
  }
}
