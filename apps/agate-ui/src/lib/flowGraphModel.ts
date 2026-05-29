import { isInputBookendType, isOutputBookendType } from '@/lib/flowValidation'
import { nodeMetadata } from '@/nodes/registry'
import {
  BOOKEND_INPUT_POSITION,
  BOOKEND_LAYOUT_X_STEP,
  BOOKEND_OUTPUT_POSITION,
} from '@/lib/flowBuilderLayout'
import { getCompatibleNextNodes, resolveEdgeHandles } from '@/lib/nodeCompatibility'

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
export const LAYOUT_NODE_WIDTH = 200
export const LAYOUT_X_GAP = 72
export const LAYOUT_X_STEP = LAYOUT_NODE_WIDTH + LAYOUT_X_GAP
export const TIDY_LAYOUT_X_GAP = 72
export const TIDY_LAYOUT_X_STEP = LAYOUT_NODE_WIDTH + TIDY_LAYOUT_X_GAP
export const LAYOUT_Y_STEP = 96
export const LAYOUT_OUTPUT_MIN_X = BOOKEND_OUTPUT_POSITION.x

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

export function getNodeById(model: FlowGraphModel, nodeId: string): FlowGraphNode | null {
  if (model.inputNode.id === nodeId) return model.inputNode
  if (model.outputNode.id === nodeId) return model.outputNode
  return model.middleNodes.find((n) => n.id === nodeId) ?? null
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

export function getInvalidFlowNodeIds(model: FlowGraphModel): Set<string> {
  const invalid = new Set<string>()

  for (const edge of deriveEdges(model)) {
    if (edge.sourceHandle == null || edge.targetHandle == null) {
      invalid.add(edge.target)
    }
  }

  for (const node of [model.inputNode, ...model.middleNodes, model.outputNode]) {
    const meta = nodeMetadata.find((entry) => entry.type === node.type)
    const requiredUpstreamNodes = meta?.requiredUpstreamNodes ?? []
    if (requiredUpstreamNodes.length === 0) continue

    const ancestry = getBranchAncestry(model, node.id)
    const hasRequiredUpstream = requiredUpstreamNodes.some((type) => ancestry.includes(type))
    if (!hasRequiredUpstream) {
      invalid.add(node.id)
    }
  }

  return invalid
}

function positionedNodesById(model: FlowGraphModel): Map<string, FlowGraphNode> {
  return new Map(toReactFlowNodes(model).map((node) => [node.id, node]))
}

function positionForNewSibling(model: FlowGraphModel, parentId: string): { x: number; y: number } {
  const positioned = positionedNodesById(model)
  const parent = positioned.get(parentId)
  const existingSiblings = model.branchChildren[parentId] ?? []
  const parentPosition = parent?.position ?? { x: LAYOUT_INPUT_X, y: LAYOUT_INPUT_Y }
  return {
    x: parentPosition.x + LAYOUT_X_STEP,
    y: parentPosition.y + existingSiblings.length * LAYOUT_Y_STEP,
  }
}

function positionForNewSerialNode(model: FlowGraphModel, afterNodeId: string): { x: number; y: number } {
  const positioned = positionedNodesById(model)
  const parent = positioned.get(afterNodeId)
  const parentPosition = parent?.position ?? { x: LAYOUT_INPUT_X, y: LAYOUT_INPUT_Y }
  return {
    x: parentPosition.x + LAYOUT_X_STEP,
    y: parentPosition.y,
  }
}

function collectDownstreamMiddleNodeIds(model: FlowGraphModel, nodeId: string): Set<string> {
  const out = new Set<string>()
  const visit = (id: string) => {
    if (out.has(id)) return
    if (!model.middleNodes.some((node) => node.id === id)) return
    out.add(id)
    const serialNext = model.serialLinks[id]
    if (serialNext) visit(serialNext)
    for (const childId of model.branchChildren[id] ?? []) {
      visit(childId)
    }
  }
  visit(nodeId)
  return out
}

function positionAfter(node: FlowGraphNode): number {
  return (node.position?.x ?? 0) + LAYOUT_X_STEP
}

function outputAfterNodes(outputNode: FlowGraphNode, nodes: FlowGraphNode[]): FlowGraphNode {
  const minOutputX = Math.max(...nodes.map(positionAfter))
  if ((outputNode.position?.x ?? 0) >= minOutputX) return outputNode
  return {
    ...outputNode,
    position: {
      x: minOutputX,
      y: outputNode.position?.y ?? LAYOUT_INPUT_Y,
    },
  }
}

function shiftNeededAfterNode(insertedNode: FlowGraphNode, firstDownstreamNode: FlowGraphNode | null): number {
  const downstreamX = firstDownstreamNode?.position?.x
  if (downstreamX == null) return LAYOUT_X_STEP
  return Math.max(LAYOUT_X_STEP, positionAfter(insertedNode) - downstreamX)
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
  const branchChildren = {
    ...model.branchChildren,
    [parentId]: [...existing, newNode.id],
  }
  const draftModel: FlowGraphModel = {
    ...model,
    middleNodes: [...model.middleNodes, newNode],
    branchChildren,
  }
  const autoPosition = assignLayoutPositions(draftModel).find((node) => node.id === newNode.id)
    ?.position
  const positionedNewNode = {
    ...newNode,
    position: newNode.position ?? autoPosition ?? positionForNewSibling(model, parentId),
  }
  return applyLayoutToModel({
    ...model,
    outputNode: outputAfterNodes(model.outputNode, [positionedNewNode]),
    middleNodes: [...model.middleNodes, positionedNewNode],
    branchChildren,
  })
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
  const positionedNewNode = {
    ...newNode,
    position: newNode.position ?? positionForNewSerialNode(model, afterNodeId),
  }
  const shiftedIds = existingNext ? collectDownstreamMiddleNodeIds(model, existingNext) : new Set<string>()
  const firstDownstreamNode = existingNext ? getNodeById(model, existingNext) : null
  const downstreamShift = shiftNeededAfterNode(positionedNewNode, firstDownstreamNode)
  const middleNodes = model.middleNodes.map((node) =>
    shiftedIds.has(node.id)
      ? {
          ...node,
          position: {
            x: (node.position?.x ?? 0) + downstreamShift,
            y: node.position?.y ?? LAYOUT_INPUT_Y,
          },
        }
      : node,
  )
  if (existingNext) {
    serialLinks[newNode.id] = existingNext
  }

  const shiftedNodesById = new Map(middleNodes.map((node) => [node.id, node]))
  const downstreamNodes = existingNext
    ? [...shiftedIds].map((id) => shiftedNodesById.get(id)).filter((node): node is FlowGraphNode => node != null)
    : []
  return applyLayoutToModel({
    ...model,
    outputNode: outputAfterNodes(model.outputNode, [positionedNewNode, ...downstreamNodes]),
    middleNodes: [...middleNodes, positionedNewNode],
    serialLinks,
  })
}

export function insertBetween(
  model: FlowGraphModel,
  sourceId: string,
  targetId: string,
  newNode: FlowGraphNode,
): FlowGraphModel {
  if (model.serialLinks[sourceId] === targetId) {
    return insertAfter(model, sourceId, newNode)
  }

  if (targetId === model.outputNode.id && getBranchTipIds(model).includes(sourceId)) {
    return insertAfter(model, sourceId, newNode)
  }

  const branchChildren = model.branchChildren[sourceId] ?? []
  if (!branchChildren.includes(targetId)) {
    throw new Error('Insert-between requires an existing edge from source to target')
  }

  const serialLinks = { ...model.serialLinks, [newNode.id]: targetId }
  const nextBranchChildren = {
    ...model.branchChildren,
    [sourceId]: branchChildren.map((childId) => (childId === targetId ? newNode.id : childId)),
  }
  const positionedNewNode = {
    ...newNode,
    position: newNode.position ?? positionForNewSerialNode(model, sourceId),
  }
  const shiftedIds = collectDownstreamMiddleNodeIds(model, targetId)
  const firstDownstreamNode = getNodeById(model, targetId)
  const downstreamShift = shiftNeededAfterNode(positionedNewNode, firstDownstreamNode)
  const middleNodes = model.middleNodes.map((node) =>
    shiftedIds.has(node.id)
      ? {
          ...node,
          position: {
            x: (node.position?.x ?? 0) + downstreamShift,
            y: node.position?.y ?? LAYOUT_INPUT_Y,
          },
        }
      : node,
  )
  const shiftedNodesById = new Map(middleNodes.map((node) => [node.id, node]))
  const downstreamNodes = [...shiftedIds]
    .map((id) => shiftedNodesById.get(id))
    .filter((node): node is FlowGraphNode => node != null)

  return applyLayoutToModel({
    ...model,
    outputNode: outputAfterNodes(model.outputNode, [positionedNewNode, ...downstreamNodes]),
    middleNodes: [...middleNodes, positionedNewNode],
    branchChildren: nextBranchChildren,
    serialLinks,
  })
}

/** Remove a middle node and rewire branch children or serial links to the parent. */
export function deleteMiddleNode(model: FlowGraphModel, nodeId: string): FlowGraphModel {
  if (nodeId === model.inputNode.id || nodeId === model.outputNode.id) {
    throw new Error('Cannot delete bookend nodes')
  }
  if (!model.middleNodes.some((n) => n.id === nodeId)) {
    throw new Error(`Unknown middle node: ${nodeId}`)
  }

  const branchParent = findBranchParentId(model, nodeId)
  const serialParent = findSerialParentId(model, nodeId)
  const serialChild = model.serialLinks[nodeId]
  const parallelChildren = [...(model.branchChildren[nodeId] ?? [])]

  const branchChildren: Record<string, string[]> = { ...model.branchChildren }
  const serialLinks: Record<string, string> = { ...model.serialLinks }

  delete branchChildren[nodeId]
  delete serialLinks[nodeId]

  if (serialParent && serialLinks[serialParent] === nodeId) {
    delete serialLinks[serialParent]
  }

  const downstream: string[] = []
  if (serialChild) downstream.push(serialChild)
  downstream.push(...parallelChildren)

  const attachParent = serialParent ?? branchParent
  if (attachParent && downstream.length > 0) {
    if (serialParent) {
      serialLinks[serialParent] = downstream[0]
      if (downstream.length > 1) {
        const existing = branchChildren[attachParent] ?? []
        branchChildren[attachParent] = [...existing, ...downstream.slice(1)]
      }
    } else if (branchParent) {
      const originalList = model.branchChildren[branchParent] ?? []
      const idx = originalList.indexOf(nodeId)
      const nextList = originalList.filter((id) => id !== nodeId)
      if (idx >= 0) {
        nextList.splice(idx, 0, ...downstream)
      } else {
        nextList.push(...downstream)
      }
      if (nextList.length > 0) {
        branchChildren[branchParent] = nextList
      } else {
        delete branchChildren[branchParent]
      }
    }
  } else if (branchParent) {
    const nextList = (branchChildren[branchParent] ?? []).filter((id) => id !== nodeId)
    if (nextList.length > 0) {
      branchChildren[branchParent] = nextList
    } else {
      delete branchChildren[branchParent]
    }
  }

  const middleNodes = model.middleNodes.filter((n) => n.id !== nodeId)

  const nextModel: FlowGraphModel = {
    ...model,
    middleNodes,
    branchChildren,
    serialLinks,
  }

  return compactLayoutAfterDelete(model, nodeId, nextModel)
}

function minimumOutputXForModel(model: FlowGraphModel): number {
  const originX = model.inputNode.position?.x ?? LAYOUT_INPUT_X
  const tips = getBranchTipIds(model)
  if (tips.length === 0) {
    return originX + BOOKEND_LAYOUT_X_STEP
  }
  let minRequired = originX
  for (const tipId of tips) {
    const tip = getNodeById(model, tipId)
    if (tip) {
      minRequired = Math.max(minRequired, positionAfter(tip))
    }
  }
  return minRequired
}

function applyHorizontalShift(
  model: FlowGraphModel,
  nodeIds: Set<string>,
  deltaX: number,
  options?: { includeOutput?: boolean },
): FlowGraphModel {
  const shiftPosition = (position: { x: number; y: number } | undefined) => ({
    x: (position?.x ?? 0) + deltaX,
    y: position?.y ?? LAYOUT_INPUT_Y,
  })

  return {
    ...model,
    outputNode: options?.includeOutput
      ? { ...model.outputNode, position: shiftPosition(model.outputNode.position) }
      : model.outputNode,
    middleNodes: model.middleNodes.map((node) =>
      nodeIds.has(node.id) ? { ...node, position: shiftPosition(node.position) } : node,
    ),
  }
}

function compactLayoutAfterDelete(
  modelBefore: FlowGraphModel,
  deletedNodeId: string,
  modelAfter: FlowGraphModel,
): FlowGraphModel {
  const deletedNode = modelBefore.middleNodes.find((node) => node.id === deletedNodeId)
  if (!deletedNode) return modelAfter

  const serialChild = modelBefore.serialLinks[deletedNodeId]
  if (serialChild) {
    const childBefore = getNodeById(modelBefore, serialChild)
    const shift = shiftNeededAfterNode(deletedNode, childBefore)
    if (shift <= 0) return modelAfter
    const nodeIds = collectDownstreamMiddleNodeIds(modelAfter, serialChild)
    return applyHorizontalShift(modelAfter, nodeIds, -shift, { includeOutput: true })
  }

  const minimumOutputX = minimumOutputXForModel(modelAfter)
  const outputX = modelAfter.outputNode.position?.x ?? 0
  if (outputX <= minimumOutputX + 0.5) {
    return modelAfter
  }

  return {
    ...modelAfter,
    outputNode: {
      ...modelAfter.outputNode,
      position: {
        x: minimumOutputX,
        y: modelAfter.outputNode.position?.y ?? LAYOUT_INPUT_Y,
      },
    },
  }
}

export function deriveEdges(model: FlowGraphModel): FlowGraphEdge[] {
  const edges: FlowGraphEdge[] = []

  const addEdge = (sourceId: string, targetId: string, kind: FlowGraphEdgeKind) => {
    const sourceNode = getNodeById(model, sourceId)
    const targetNode = getNodeById(model, targetId)
    const handles =
      sourceNode?.type && targetNode?.type
        ? resolveEdgeHandles(sourceNode.type, targetNode.type)
        : null
    edges.push({
      id: `${sourceId}-${targetId}`,
      source: sourceId,
      target: targetId,
      kind,
      sourceHandle: handles?.sourceHandle,
      targetHandle: handles?.targetHandle,
    })
  }

  for (const [parentId, children] of Object.entries(model.branchChildren)) {
    for (const childId of children) {
      addEdge(parentId, childId, 'branch')
    }
  }

  for (const [source, target] of Object.entries(model.serialLinks)) {
    addEdge(source, target, 'serial')
  }

  for (const tipId of getBranchTipIds(model)) {
    addEdge(tipId, model.outputNode.id, 'tip')
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

export function assignLayoutPositions(
  model: FlowGraphModel,
  options?: { xStep?: number },
): FlowGraphNode[] {
  const slots = assignLayoutSlots(model)
  const positioned: FlowGraphNode[] = []
  const originX = model.inputNode.position?.x ?? LAYOUT_INPUT_X
  const originY = model.inputNode.position?.y ?? LAYOUT_INPUT_Y
  const xStep =
    options?.xStep ?? (model.middleNodes.length === 0 ? BOOKEND_LAYOUT_X_STEP : LAYOUT_X_STEP)

  let maxDepth = 0
  for (const { depth } of slots.values()) {
    maxDepth = Math.max(maxDepth, depth)
  }

  const slotValues = [...slots.values()].map((s) => s.slot)
  const minSlot = slotValues.length > 0 ? Math.min(...slotValues) : 0
  const maxSlot = slotValues.length > 0 ? Math.max(...slotValues) : 0
  const slotCenter = (minSlot + maxSlot) / 2

  let orphanDepth = 0
  const positionFor = (nodeId: string, fallbackY: number) => {
    const slot = slots.get(nodeId)
    if (!slot) {
      orphanDepth += 1
      return {
        x: originX + orphanDepth * xStep,
        y: fallbackY,
      }
    }
    return {
      x: originX + slot.depth * xStep,
      y: originY + (slot.slot - slotCenter) * LAYOUT_Y_STEP,
    }
  }

  positioned.push({
    ...model.inputNode,
    position: positionFor(model.inputNode.id, originY),
  })

  for (const middle of model.middleNodes) {
    positioned.push({
      ...middle,
      position: positionFor(middle.id, originY),
    })
  }

  const outputX = originX + (maxDepth + 1) * xStep
  positioned.push({
    ...model.outputNode,
    position: { x: outputX, y: originY },
  })

  return positioned
}

/** Recompute layout positions and persist them on the model nodes. */
export function applyLayoutToModel(
  model: FlowGraphModel,
  options?: { relayoutBookends?: boolean; xStep?: number },
): FlowGraphModel {
  const relayoutBookends = options?.relayoutBookends ?? false
  const positioned = assignLayoutPositions(model, { xStep: options?.xStep })
  const byId = new Map(positioned.map((n) => [n.id, n.position]))

  const bookendInputPosition = (node: FlowGraphNode) => {
    const auto = byId.get(node.id)
    if (relayoutBookends) {
      return auto ?? node.position ?? { x: 0, y: 0 }
    }
    return node.position ?? auto ?? { x: 0, y: 0 }
  }

  return {
    ...model,
    inputNode: {
      ...model.inputNode,
      position: bookendInputPosition(model.inputNode),
    },
    outputNode: {
      ...model.outputNode,
      position: relayoutBookends
        ? (byId.get(model.outputNode.id) ?? model.outputNode.position ?? { x: 0, y: 0 })
        : (model.outputNode.position ?? byId.get(model.outputNode.id) ?? { x: 0, y: 0 }),
    },
    middleNodes: model.middleNodes.map((n) => ({
      ...n,
      position: relayoutBookends
        ? (byId.get(n.id) ?? n.position ?? { x: 0, y: 0 })
        : (n.position ?? byId.get(n.id) ?? { x: 0, y: 0 }),
    })),
  }
}

export function toReactFlowNodes(model: FlowGraphModel): FlowGraphNode[] {
  const layoutDefaults = assignLayoutPositions(model)
  const defaultById = new Map(layoutDefaults.map((node) => [node.id, node.position!]))

  const withStoredOrDefault = (node: FlowGraphNode): FlowGraphNode => ({
    ...node,
    position: node.position ?? defaultById.get(node.id) ?? { x: 0, y: 0 },
  })

  return [
    withStoredOrDefault(model.inputNode),
    ...model.middleNodes.map(withStoredOrDefault),
    withStoredOrDefault(model.outputNode),
  ]
}

export function updateNodePosition(
  model: FlowGraphModel,
  nodeId: string,
  position: { x: number; y: number },
): FlowGraphModel {
  if (model.inputNode.id === nodeId) {
    return { ...model, inputNode: { ...model.inputNode, position } }
  }
  if (model.outputNode.id === nodeId) {
    return { ...model, outputNode: { ...model.outputNode, position } }
  }
  if (model.middleNodes.some((node) => node.id === nodeId)) {
    return {
      ...model,
      middleNodes: model.middleNodes.map((node) =>
        node.id === nodeId ? { ...node, position } : node,
      ),
    }
  }
  return model
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

export type SavedGraphSpecNode = {
  id: string
  type: string
  params?: Record<string, unknown>
  position?: { x: number; y: number }
}

export type SavedGraphSpecEdge = {
  source: string
  target: string
  sourceHandle?: string | null
  targetHandle?: string | null
}

export type SavedGraphSpec = {
  nodes: SavedGraphSpecNode[]
  edges?: SavedGraphSpecEdge[]
}

export type HydrateFromSpecFailure = {
  ok: false
  title: string
  description: string
}

export type HydrateFromSpecResult = { ok: true; model: FlowGraphModel } | HydrateFromSpecFailure

const LAYOUT_Y_EPSILON = 2

function specNodeToFlowNode(node: SavedGraphSpecNode): FlowGraphNode {
  return {
    id: node.id,
    type: node.type,
    data: { ...(node.params ?? {}) },
    position: node.position,
  }
}

export function isMiddleNodeId(model: FlowGraphModel, nodeId: string): boolean {
  return model.middleNodes.some((n) => n.id === nodeId)
}

export type BookendSwapCheck = { ok: true } | { ok: false; reason: string }

function nodeTypeLabel(type: string): string {
  return nodeMetadata.find((meta) => meta.type === type)?.label ?? type
}

/** Whether a new input bookend type can connect to existing first-hop middle steps. */
export function canReplaceInputBookend(model: FlowGraphModel, newType: string): BookendSwapCheck {
  const childIds = model.branchChildren[model.inputNode.id] ?? []
  if (childIds.length === 0) return { ok: true }

  const { enabled } = getCompatibleNextNodes(newType, [newType])
  const enabledTypes = new Set(enabled.map((entry) => entry.type))

  for (const childId of childIds) {
    const child = getNodeById(model, childId)
    if (!child?.type) continue
    if (!enabledTypes.has(child.type)) {
      return {
        ok: false,
        reason: `“${nodeTypeLabel(child.type)}” cannot connect to this content source. Remove or change that step first.`,
      }
    }
  }

  return { ok: true }
}

/** Whether branch tips can still connect to a new output bookend type. */
export function canReplaceOutputBookend(model: FlowGraphModel, newType: string): BookendSwapCheck {
  for (const tipId of getBranchTipIds(model)) {
    const tip = getNodeById(model, tipId)
    if (!tip?.type) continue
    if (!resolveEdgeHandles(tip.type, newType)) {
      return {
        ok: false,
        reason: `“${nodeTypeLabel(tip.type)}” cannot connect to this destination. Remove or change that step first.`,
      }
    }
  }

  return { ok: true }
}

/** Swap input bookend type/data; middle topology and node id are preserved. */
export function replaceInputBookend(
  model: FlowGraphModel,
  patch: { type: string; data?: Record<string, unknown> },
): FlowGraphModel {
  return applyLayoutToModel({
    ...model,
    inputNode: {
      ...model.inputNode,
      type: patch.type,
      data: patch.data ?? model.inputNode.data,
    },
  })
}

/** Swap output bookend type/data; middle topology and node id are preserved. */
export function replaceOutputBookend(
  model: FlowGraphModel,
  patch: { type: string; data?: Record<string, unknown> },
): FlowGraphModel {
  return applyLayoutToModel({
    ...model,
    outputNode: {
      ...model.outputNode,
      type: patch.type,
      data: patch.data ?? model.outputNode.data,
    },
  })
}

/** Remove all middle nodes and internal edges; bookends are preserved. */
export function clearMiddleNodes(model: FlowGraphModel): FlowGraphModel {
  return applyLayoutToModel({
    ...model,
    middleNodes: [],
    branchChildren: {},
    serialLinks: {},
  })
}

function classifyOutgoingEdges(
  sourceId: string,
  inputId: string,
  targets: string[],
  positions: Map<string, { x: number; y: number }>,
): { serial?: string; branch: string[] } {
  const uniqueTargets = [...new Set(targets)]
  if (uniqueTargets.length === 0) {
    return { branch: [] }
  }
  if (sourceId === inputId) {
    return { branch: uniqueTargets }
  }
  if (uniqueTargets.length === 1) {
    return { serial: uniqueTargets[0], branch: [] }
  }

  const parentY = positions.get(sourceId)?.y ?? 0
  const sameRow = uniqueTargets.filter(
    (targetId) => Math.abs((positions.get(targetId)?.y ?? 0) - parentY) <= LAYOUT_Y_EPSILON,
  )

  if (sameRow.length === 1) {
    return {
      serial: sameRow[0],
      branch: uniqueTargets.filter((id) => id !== sameRow[0]),
    }
  }

  const byDepth = [...uniqueTargets].sort(
    (a, b) => (positions.get(b)?.x ?? 0) - (positions.get(a)?.x ?? 0),
  )
  return {
    serial: byDepth[0],
    branch: uniqueTargets.filter((id) => id !== byDepth[0]),
  }
}

function buildTopologyFromSpec(
  inputId: string,
  outputId: string,
  middleIds: Set<string>,
  edges: SavedGraphSpecEdge[],
  positions: Map<string, { x: number; y: number }>,
): { branchChildren: Record<string, string[]>; serialLinks: Record<string, string> } {
  const branchChildren: Record<string, string[]> = {}
  const serialLinks: Record<string, string> = {}
  const outgoing = new Map<string, string[]>()

  for (const edge of edges) {
    if (edge.target === outputId) continue
    if (edge.source === outputId) continue
    const list = outgoing.get(edge.source) ?? []
    list.push(edge.target)
    outgoing.set(edge.source, list)
  }

  for (const [sourceId, targets] of outgoing) {
    const middleTargets = targets.filter((targetId) => middleIds.has(targetId))
    if (middleTargets.length === 0) continue

    const { serial, branch } = classifyOutgoingEdges(sourceId, inputId, middleTargets, positions)
    if (branch.length > 0) {
      branchChildren[sourceId] = branch
    }
    if (serial) {
      serialLinks[sourceId] = serial
    }
  }

  return { branchChildren, serialLinks }
}

/** Parse a saved graph spec into a guided FlowGraphModel. */
export function hydrateFromSpec(spec: SavedGraphSpec): HydrateFromSpecResult {
  const nodes = spec.nodes ?? []
  const inputNodes = nodes.filter((n) => isInputBookendType(n.type))
  const outputNodes = nodes.filter((n) => isOutputBookendType(n.type))

  if (inputNodes.length === 0) {
    return {
      ok: false,
      title: 'Missing content source',
      description: 'This flow needs one place where content comes in before it can be edited here.',
    }
  }
  if (inputNodes.length > 1) {
    return {
      ok: false,
      title: 'Too many content sources',
      description:
        'This flow has more than one content source. Open it in the classic editor or rebuild it with a single source.',
    }
  }
  if (outputNodes.length === 0) {
    return {
      ok: false,
      title: 'Missing destination',
      description: 'This flow needs one place where results are saved before it can be edited here.',
    }
  }
  if (outputNodes.length > 1) {
    return {
      ok: false,
      title: 'Too many destinations',
      description:
        'This flow has more than one destination. Open it in the classic editor or rebuild it with a single output.',
    }
  }

  const inputNode = specNodeToFlowNode(inputNodes[0])
  const outputNode = specNodeToFlowNode(outputNodes[0])
  const bookendIds = new Set([inputNode.id, outputNode.id])
  const middleNodes = nodes
    .filter((n) => !bookendIds.has(n.id))
    .map(specNodeToFlowNode)
  const middleIds = new Set(middleNodes.map((n) => n.id))

  const positions = new Map<string, { x: number; y: number }>()
  for (const node of nodes) {
    positions.set(node.id, {
      x: node.position?.x ?? 0,
      y: node.position?.y ?? 0,
    })
  }

  const { branchChildren, serialLinks } = buildTopologyFromSpec(
    inputNode.id,
    outputNode.id,
    middleIds,
    spec.edges ?? [],
    positions,
  )

  return {
    ok: true,
    model: {
      inputNode,
      outputNode,
      middleNodes,
      branchChildren,
      serialLinks,
    },
  }
}

export function modelToGraphSpec(model: FlowGraphModel): {
  nodes: Array<{
    id: string
    type: string
    params: Record<string, unknown>
    position: { x: number; y: number }
  }>
  edges: Array<{
    source: string
    target: string
    sourceHandle: string | null
    targetHandle: string | null
  }>
} {
  const positioned = toReactFlowNodes(model)
  return {
    nodes: positioned.map((node) => ({
      id: node.id,
      type: node.type ?? '',
      params: { ...(node.data ?? {}) },
      position: node.position ?? { x: 0, y: 0 },
    })),
    edges: deriveEdges(model).map((edge) => ({
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle ?? null,
      targetHandle: edge.targetHandle ?? null,
    })),
  }
}
