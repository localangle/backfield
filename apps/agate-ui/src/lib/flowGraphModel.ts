import { INPUT_BOOKEND_TYPES, OUTPUT_BOOKEND_TYPES } from '@/lib/flowValidation'
import { BOOKEND_INPUT_POSITION, BOOKEND_OUTPUT_POSITION } from '@/lib/flowBuilderLayout'

export type FlowGraphNode = {
  id: string
  type: string
  data?: Record<string, unknown>
  position?: { x: number; y: number }
}

export type FlowGraphEdgeKind = 'branch' | 'serial' | 'tip'

export type FlowGraphEdge = {
  id: string
  source: string
  target: string
  kind: FlowGraphEdgeKind
  sourceHandle?: string
  targetHandle?: string
}

export type FlowGraphModel = {
  inputNode: FlowGraphNode
  outputNode: FlowGraphNode
  middleNodes: FlowGraphNode[]
  /** Parallel direct children keyed by parent node id. */
  branchChildren: Record<string, string[]>
  /** Serial next step within a branch (at most one per node). */
  serialLinks: Record<string, string>
}

export const LAYOUT_INPUT_X = BOOKEND_INPUT_POSITION.x
export const LAYOUT_INPUT_Y = BOOKEND_INPUT_POSITION.y
export const LAYOUT_X_STEP = 160
export const LAYOUT_Y_STEP = 140
export const LAYOUT_OUTPUT_MIN_X = BOOKEND_OUTPUT_POSITION.x
export const LAYOUT_NODE_WIDTH = 280

/** @deprecated Use LAYOUT_X_STEP */
export const MIDDLE_NODE_X_START = 220
/** @deprecated Use LAYOUT_X_STEP */
export const MIDDLE_NODE_X_STEP = 140

export function createFlowGraphModel(
  inputNode: FlowGraphNode,
  outputNode: FlowGraphNode,
): FlowGraphModel {
  return {
    inputNode,
    outputNode,
    middleNodes: [],
    branchChildren: {},
    serialLinks: {},
  }
}

export function isInputBookendType(type: string | undefined): boolean {
  return type != null && (INPUT_BOOKEND_TYPES as readonly string[]).includes(type)
}

export function isOutputBookendType(type: string | undefined): boolean {
  return type != null && (OUTPUT_BOOKEND_TYPES as readonly string[]).includes(type)
}

export function getNodeById(model: FlowGraphModel, nodeId: string): FlowGraphNode | null {
  if (model.inputNode.id === nodeId) return model.inputNode
  if (model.outputNode.id === nodeId) return model.outputNode
  return model.middleNodes.find((n) => n.id === nodeId) ?? null
}

export function getSerialChildId(model: FlowGraphModel, parentId: string): string | null {
  return model.serialLinks[parentId] ?? null
}

function findSerialParentId(model: FlowGraphModel, childId: string): string | null {
  for (const [parentId, nextId] of Object.entries(model.serialLinks)) {
    if (nextId === childId) return parentId
  }
  return null
}

function findBranchParentId(model: FlowGraphModel, childId: string): string | null {
  for (const [parentId, children] of Object.entries(model.branchChildren)) {
    if (children.includes(childId)) return parentId
  }
  return null
}

function getMiddleSuccessors(model: FlowGraphModel, nodeId: string): string[] {
  const out = [...(model.branchChildren[nodeId] ?? [])]
  const serial = model.serialLinks[nodeId]
  if (serial) out.push(serial)
  return out
}

/** Types on the path from input to `nodeId`, including that node. */
export function getBranchAncestry(model: FlowGraphModel, nodeId: string): string[] {
  const types: string[] = []
  let current: string | null = nodeId
  const visited = new Set<string>()

  while (current && !visited.has(current)) {
    visited.add(current)
    const node = getNodeById(model, current)
    if (!node?.type) break
    types.unshift(node.type)
    const serialParent = findSerialParentId(model, current)
    if (serialParent) {
      current = serialParent
      continue
    }
    current = findBranchParentId(model, current)
  }

  return types
}

/** Branch tip node ids: nodes with no outgoing middle edges (excluding output bookend). */
export function getBranchTipIds(model: FlowGraphModel): string[] {
  const allIds = [model.inputNode.id, ...model.middleNodes.map((n) => n.id)]
  return allIds.filter((id) => getMiddleSuccessors(model, id).length === 0)
}

export function addSiblingBranch(
  model: FlowGraphModel,
  parentId: string,
  newNode: FlowGraphNode,
): FlowGraphModel {
  if (parentId === model.outputNode.id) {
    throw new Error('Cannot add a child to the output bookend')
  }
  if (getNodeById(model, parentId) == null) {
    throw new Error(`Unknown parent node: ${parentId}`)
  }

  const existing = model.branchChildren[parentId] ?? []
  return {
    ...model,
    middleNodes: [...model.middleNodes, newNode],
    branchChildren: {
      ...model.branchChildren,
      [parentId]: [...existing, newNode.id],
    },
  }
}

/** Insert or extend serially after `afterNodeId`, pushing any existing serial child downstream. */
export function insertAfter(
  model: FlowGraphModel,
  afterNodeId: string,
  newNode: FlowGraphNode,
): FlowGraphModel {
  if (afterNodeId === model.outputNode.id) {
    throw new Error('Cannot insert after the output bookend')
  }
  if (getNodeById(model, afterNodeId) == null) {
    throw new Error(`Unknown node: ${afterNodeId}`)
  }

  const existingNext = model.serialLinks[afterNodeId]
  const serialLinks = { ...model.serialLinks, [afterNodeId]: newNode.id }
  if (existingNext) {
    serialLinks[newNode.id] = existingNext
  }

  return {
    ...model,
    middleNodes: [...model.middleNodes, newNode],
    serialLinks,
  }
}

export function insertBetween(
  model: FlowGraphModel,
  sourceId: string,
  targetId: string,
  newNode: FlowGraphNode,
): FlowGraphModel {
  if (model.serialLinks[sourceId] !== targetId) {
    throw new Error('Insert-between requires a serial edge from source to target')
  }
  return insertAfter(model, sourceId, newNode)
}

/** @deprecated Use insertAfter for serial extension or addSiblingBranch for parallel branches. */
export function addSerialChild(
  model: FlowGraphModel,
  parentId: string,
  newNode: FlowGraphNode,
): FlowGraphModel {
  return insertAfter(model, parentId, newNode)
}

export function deriveEdges(model: FlowGraphModel): FlowGraphEdge[] {
  const edges: FlowGraphEdge[] = []

  for (const [parentId, children] of Object.entries(model.branchChildren)) {
    for (const childId of children) {
      edges.push({
        id: `${parentId}-${childId}`,
        source: parentId,
        target: childId,
        kind: 'branch',
      })
    }
  }

  for (const [source, target] of Object.entries(model.serialLinks)) {
    edges.push({
      id: `${source}-${target}`,
      source,
      target,
      kind: 'serial',
    })
  }

  for (const tipId of getBranchTipIds(model)) {
    edges.push({
      id: `${tipId}-${model.outputNode.id}`,
      source: tipId,
      target: model.outputNode.id,
      kind: 'tip',
    })
  }

  return edges
}

type LayoutSlot = { depth: number; slot: number }

function assignLayoutSlots(model: FlowGraphModel): Map<string, LayoutSlot> {
  const slots = new Map<string, LayoutSlot>()
  slots.set(model.inputNode.id, { depth: 0, slot: 0 })

  const roots = model.branchChildren[model.inputNode.id] ?? []
  roots.forEach((rootId, branchIndex) => {
    walkBranchLayout(model, rootId, 1, branchIndex, slots)
  })

  return slots
}

function walkBranchLayout(
  model: FlowGraphModel,
  nodeId: string,
  depth: number,
  slot: number,
  slots: Map<string, LayoutSlot>,
): void {
  slots.set(nodeId, { depth, slot })

  const serialNext = model.serialLinks[nodeId]
  if (serialNext) {
    walkBranchLayout(model, serialNext, depth + 1, slot, slots)
  }

  const parallelChildren = model.branchChildren[nodeId] ?? []
  parallelChildren.forEach((childId, index) => {
    walkBranchLayout(model, childId, depth + 1, slot + index + 1, slots)
  })
}

export function assignLayoutPositions(model: FlowGraphModel): FlowGraphNode[] {
  const slots = assignLayoutSlots(model)
  const positioned: FlowGraphNode[] = []

  let maxDepth = 0
  for (const { depth } of slots.values()) {
    maxDepth = Math.max(maxDepth, depth)
  }

  const slotValues = [...slots.values()].map((s) => s.slot)
  const minSlot = slotValues.length > 0 ? Math.min(...slotValues) : 0
  const maxSlot = slotValues.length > 0 ? Math.max(...slotValues) : 0
  const slotCenter = (minSlot + maxSlot) / 2

  const positionFor = (nodeId: string, fallbackY: number) => {
    const slot = slots.get(nodeId)
    if (!slot) {
      return { x: LAYOUT_INPUT_X, y: fallbackY }
    }
    return {
      x: LAYOUT_INPUT_X + slot.depth * LAYOUT_X_STEP,
      y: LAYOUT_INPUT_Y + (slot.slot - slotCenter) * LAYOUT_Y_STEP,
    }
  }

  positioned.push({
    ...model.inputNode,
    position: positionFor(model.inputNode.id, LAYOUT_INPUT_Y),
  })

  for (const middle of model.middleNodes) {
    positioned.push({
      ...middle,
      position: positionFor(middle.id, LAYOUT_INPUT_Y),
    })
  }

  const outputX = Math.max(LAYOUT_OUTPUT_MIN_X, LAYOUT_INPUT_X + (maxDepth + 1) * LAYOUT_X_STEP + 40)
  positioned.push({
    ...model.outputNode,
    position: { x: outputX, y: LAYOUT_INPUT_Y },
  })

  return positioned
}

/** Recompute layout positions and persist them on the model nodes. */
export function applyLayoutToModel(model: FlowGraphModel): FlowGraphModel {
  const positioned = assignLayoutPositions(model)
  const byId = new Map(positioned.map((n) => [n.id, n.position]))

  return {
    ...model,
    inputNode: {
      ...model.inputNode,
      position: byId.get(model.inputNode.id) ?? model.inputNode.position,
    },
    outputNode: {
      ...model.outputNode,
      position: byId.get(model.outputNode.id) ?? model.outputNode.position,
    },
    middleNodes: model.middleNodes.map((n) => ({
      ...n,
      position: byId.get(n.id) ?? n.position,
    })),
  }
}

export function toReactFlowNodes(model: FlowGraphModel): FlowGraphNode[] {
  return assignLayoutPositions(model)
}

export function updateMiddleNodeData(
  model: FlowGraphModel,
  nodeId: string,
  data: Record<string, unknown>,
): FlowGraphModel {
  return {
    ...model,
    middleNodes: model.middleNodes.map((n) =>
      n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n,
    ),
  }
}

export function updateMiddleNode(
  model: FlowGraphModel,
  nodeId: string,
  updater: (node: FlowGraphNode) => FlowGraphNode,
): FlowGraphModel {
  return {
    ...model,
    middleNodes: model.middleNodes.map((n) => (n.id === nodeId ? updater(n) : n)),
  }
}
