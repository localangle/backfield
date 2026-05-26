import { describe, expect, it } from 'vitest'
import { BOOKEND_OUTPUT_POSITION } from './flowBuilderLayout'
import {
  addSiblingBranch,
  applyLayoutToModel,
  assignLayoutPositions,
  canReplaceInputBookend,
  canReplaceOutputBookend,
  clearMiddleNodes,
  replaceInputBookend,
  createFlowGraphModel,
  deleteMiddleNode,
  deriveEdges,
  getBranchAncestry,
  getBranchTipIds,
  hydrateFromSpec,
  insertAfter,
  insertBetween,
  isMiddleNodeId,
  LAYOUT_NODE_WIDTH,
  LAYOUT_X_GAP,
  LAYOUT_X_STEP,
  modelToGraphSpec,
  toReactFlowNodes,
  updateNodePosition,
  type FlowGraphNode,
} from './flowGraphModel'

function bookends() {
  const inputNode: FlowGraphNode = { id: 'input-1', type: 'TextInput', data: { text: 'hi' } }
  const outputNode: FlowGraphNode = { id: 'output-1', type: 'Output', data: {} }
  return createFlowGraphModel(inputNode, outputNode)
}

function edgeSet(model: ReturnType<typeof bookends>) {
  return new Set(deriveEdges(model).map((e) => `${e.source}->${e.target}:${e.kind}`))
}

describe('flowGraphModel serial chain', () => {
  it('connects branch tips to output when middle is empty', () => {
    const model = bookends()
    expect(edgeSet(model)).toEqual(new Set(['input-1->output-1:tip']))
    expect(getBranchTipIds(model)).toEqual(['input-1'])
  })

  it('adds PlaceExtract as a branch from input with tip wired to output', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const model = addSiblingBranch(bookends(), 'input-1', place)
    expect(edgeSet(model)).toEqual(
      new Set(['input-1->place-1:branch', 'place-1->output-1:tip']),
    )
    const edges = deriveEdges(model)
    const inputToPlace = edges.find((e) => e.source === 'input-1' && e.target === 'place-1')
    const placeToOutput = edges.find((e) => e.source === 'place-1' && e.target === 'output-1')
    expect(inputToPlace?.sourceHandle).toBe('text')
    expect(inputToPlace?.targetHandle).toBe('text')
    expect(placeToOutput?.sourceHandle).toBe('locations')
    expect(placeToOutput?.targetHandle).toBe('data')
    expect(getBranchTipIds(model)).toEqual(['place-1'])
  })

  it('extends a branch serially with Geocode and removes direct place-to-output edge', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const geocode: FlowGraphNode = { id: 'geo-1', type: 'GeocodeAgent', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = insertAfter(model, 'place-1', geocode)

    expect(edgeSet(model)).toEqual(
      new Set([
        'input-1->place-1:branch',
        'place-1->geo-1:serial',
        'geo-1->output-1:tip',
      ]),
    )
    expect(getBranchTipIds(model)).toEqual(['geo-1'])
  })

  it('inserts serially after a node and preserves existing downstream child', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const geocode: FlowGraphNode = { id: 'geo-1', type: 'GeocodeAgent', data: {} }
    const inserted: FlowGraphNode = { id: 'filter-1', type: 'PlaceExtract', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = insertAfter(model, 'place-1', geocode)
    model = insertAfter(model, 'place-1', inserted)

    expect(model.serialLinks['place-1']).toBe('filter-1')
    expect(model.serialLinks['filter-1']).toBe('geo-1')
    expect(edgeSet(model)).toEqual(
      new Set([
        'input-1->place-1:branch',
        'place-1->filter-1:serial',
        'filter-1->geo-1:serial',
        'geo-1->output-1:tip',
      ]),
    )
  })

  it('computes branch ancestry from input through middle nodes', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const geocode: FlowGraphNode = { id: 'geo-1', type: 'GeocodeAgent', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = insertAfter(model, 'place-1', geocode)

    expect(getBranchAncestry(model, 'geo-1')).toEqual([
      'TextInput',
      'PlaceExtract',
      'GeocodeAgent',
    ])
  })
})

describe('flowGraphModel parallel branches', () => {
  it('creates two sibling branches from input with separate tips to output', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const place2: FlowGraphNode = { id: 'place-2', type: 'PlaceExtract', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = addSiblingBranch(model, 'input-1', place2)

    expect(model.branchChildren['input-1']).toEqual(['place-1', 'place-2'])
    expect(getBranchTipIds(model)).toEqual(['place-1', 'place-2'])
    expect(edgeSet(model)).toEqual(
      new Set([
        'input-1->place-1:branch',
        'input-1->place-2:branch',
        'place-1->output-1:tip',
        'place-2->output-1:tip',
      ]),
    )
  })

  it('keeps serial extension on one branch only when the other branch is parallel', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const place2: FlowGraphNode = { id: 'place-2', type: 'PlaceExtract', data: {} }
    const geocode: FlowGraphNode = { id: 'geo-1', type: 'GeocodeAgent', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = addSiblingBranch(model, 'input-1', place2)
    model = insertAfter(model, 'place-1', geocode)

    expect(new Set(getBranchTipIds(model))).toEqual(new Set(['geo-1', 'place-2']))
    expect(edgeSet(model)).toEqual(
      new Set([
        'input-1->place-1:branch',
        'input-1->place-2:branch',
        'place-1->geo-1:serial',
        'geo-1->output-1:tip',
        'place-2->output-1:tip',
      ]),
    )
  })

  it('inserts between serial nodes via insertBetween', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const geocode: FlowGraphNode = { id: 'geo-1', type: 'GeocodeAgent', data: {} }
    const middle: FlowGraphNode = { id: 'mid-1', type: 'PlaceExtract', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = insertAfter(model, 'place-1', geocode)
    model = insertBetween(model, 'place-1', 'geo-1', middle)

    expect(model.serialLinks['place-1']).toBe('mid-1')
    expect(model.serialLinks['mid-1']).toBe('geo-1')
  })
})

describe('flowGraphModel layout', () => {
  it('fans parallel siblings vertically and serial steps horizontally', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const place2: FlowGraphNode = { id: 'place-2', type: 'PlaceExtract', data: {} }
    const geocode: FlowGraphNode = { id: 'geo-1', type: 'GeocodeAgent', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = addSiblingBranch(model, 'input-1', place2)
    model = insertAfter(model, 'place-1', geocode)

    const positioned = assignLayoutPositions(model)
    const byId = new Map(positioned.map((n) => [n.id, n.position!]))

    expect(byId.get('place-1')!.x).toBeLessThan(byId.get('geo-1')!.x)
    expect(byId.get('place-1')!.y).not.toBe(byId.get('place-2')!.y)
    expect(byId.get('output-1')!.x).toBeGreaterThan(byId.get('geo-1')!.x)
  })

  it('spaces the first middle step to the right of the input bookend', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const model = addSiblingBranch(bookends(), 'input-1', place)
    const positioned = assignLayoutPositions(model)
    const byId = new Map(positioned.map((n) => [n.id, n.position!]))

    const inputRight = byId.get('input-1')!.x + LAYOUT_NODE_WIDTH
    expect(byId.get('place-1')!.x).toBeGreaterThanOrEqual(inputRight)
  })

  it('toReactFlowNodes prefers stored positions over auto layout', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = updateNodePosition(model, 'place-1', { x: 900, y: 400 })

    const nodes = toReactFlowNodes(model)
    expect(nodes.find((node) => node.id === 'place-1')?.position).toEqual({ x: 900, y: 400 })
  })

  it('applyLayoutToModel preserves dragged input and relayouts output when middle steps exist', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = updateNodePosition(model, 'input-1', { x: 120, y: 300 })
    model = updateNodePosition(model, 'output-1', { x: 520, y: 300 })

    const afterAdd = applyLayoutToModel(model)
    const auto = assignLayoutPositions(model)
    expect(afterAdd.inputNode.position).toEqual({ x: 120, y: 300 })
    expect(afterAdd.outputNode.position).toEqual(auto.find((node) => node.id === 'output-1')?.position)
    const middleX = afterAdd.middleNodes.find((node) => node.id === 'place-1')?.position?.x ?? 0
    expect(afterAdd.outputNode.position!.x).toBeGreaterThan(middleX + LAYOUT_NODE_WIDTH)

    const tidied = applyLayoutToModel(model, { relayoutBookends: true })
    expect(tidied.inputNode.position).toEqual(auto.find((node) => node.id === 'input-1')?.position)
    expect(tidied.outputNode.position).toEqual(auto.find((node) => node.id === 'output-1')?.position)
  })

  it('addSiblingBranch spaces output past new middle nodes', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const model = addSiblingBranch(
      {
        ...bookends(),
        outputNode: { ...bookends().outputNode, position: BOOKEND_OUTPUT_POSITION },
      },
      'input-1',
      place,
    )
    const middleX = model.middleNodes[0]?.position?.x ?? 0
    const gapBeforeOutput = model.outputNode.position!.x - (middleX + LAYOUT_NODE_WIDTH)
    expect(gapBeforeOutput).toBe(LAYOUT_X_GAP)
    expect(model.outputNode.position!.x).toBeGreaterThan(middleX + LAYOUT_NODE_WIDTH)
  })

  it('serial chain uses consistent horizontal gaps between nodes', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = insertAfter(model, 'place-1', { id: 'geo-1', type: 'GeocodeAgent', data: {} })

    const nodes = toReactFlowNodes(model)
    const input = nodes.find((n) => n.id === 'input-1')!
    const placeNode = nodes.find((n) => n.id === 'place-1')!
    const geo = nodes.find((n) => n.id === 'geo-1')!
    const output = nodes.find((n) => n.id === 'output-1')!

    expect(placeNode.position!.x - (input.position!.x + LAYOUT_NODE_WIDTH)).toBe(LAYOUT_X_GAP)
    expect(geo.position!.x - (placeNode.position!.x + LAYOUT_NODE_WIDTH)).toBe(LAYOUT_X_GAP)
    expect(output.position!.x - (geo.position!.x + LAYOUT_NODE_WIDTH)).toBe(LAYOUT_X_GAP)
    expect(input.position!.y).toBe(placeNode.position!.y)
    expect(placeNode.position!.y).toBe(geo.position!.y)
    expect(geo.position!.y).toBe(output.position!.y)
  })

  it('applyLayoutToModel preserves dragged middle positions unless relayoutBookends', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = updateNodePosition(model, 'place-1', { x: 900, y: 400 })

    const relayouted = applyLayoutToModel(model)
    expect(relayouted.middleNodes.find((node) => node.id === 'place-1')?.position).toEqual({
      x: 900,
      y: 400,
    })

    const tidied = applyLayoutToModel(model, { relayoutBookends: true })
    const auto = assignLayoutPositions(model)
    expect(tidied.middleNodes.find((node) => node.id === 'place-1')?.position).toEqual(
      auto.find((node) => node.id === 'place-1')?.position,
    )
  })
})

describe('flowGraphModel deleteMiddleNode', () => {
  it('rejects deleting bookend nodes', () => {
    const model = bookends()
    expect(() => deleteMiddleNode(model, 'input-1')).toThrow(/bookend/i)
    expect(() => deleteMiddleNode(model, 'output-1')).toThrow(/bookend/i)
  })

  it('rewires serial downstream when deleting a middle step', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const geocode: FlowGraphNode = { id: 'geo-1', type: 'GeocodeAgent', data: {} }
    const middle: FlowGraphNode = { id: 'mid-1', type: 'PlaceExtract', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = insertAfter(model, 'place-1', middle)
    model = insertAfter(model, 'mid-1', geocode)

    model = deleteMiddleNode(model, 'mid-1')

    expect(model.serialLinks['place-1']).toBe('geo-1')
    expect(model.middleNodes.map((n) => n.id)).toEqual(['place-1', 'geo-1'])
    expect(edgeSet(model)).toEqual(
      new Set([
        'input-1->place-1:branch',
        'place-1->geo-1:serial',
        'geo-1->output-1:tip',
      ]),
    )
  })

  it('removes a parallel branch tip while keeping the other branch intact', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const place2: FlowGraphNode = { id: 'place-2', type: 'PlaceExtract', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = addSiblingBranch(model, 'input-1', place2)

    model = deleteMiddleNode(model, 'place-2')

    expect(model.branchChildren['input-1']).toEqual(['place-1'])
    expect(getBranchTipIds(model)).toEqual(['place-1'])
    expect(model.middleNodes.map((n) => n.id)).toEqual(['place-1'])
  })

  it('restores input as a tip when the only branch step is deleted', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = deleteMiddleNode(model, 'place-1')

    expect(model.branchChildren['input-1']).toBeUndefined()
    expect(getBranchTipIds(model)).toEqual(['input-1'])
    expect(model.middleNodes).toHaveLength(0)
    expect(edgeSet(model)).toEqual(new Set(['input-1->output-1:tip']))
  })

  it('clears serial link when deleting a leaf step on a branch', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const geocode: FlowGraphNode = { id: 'geo-1', type: 'GeocodeAgent', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = insertAfter(model, 'place-1', geocode)
    model = deleteMiddleNode(model, 'geo-1')

    expect(model.serialLinks['place-1']).toBeUndefined()
    expect(getBranchTipIds(model)).toEqual(['place-1'])
  })
})

describe('flowGraphModel hydrate and edit helpers', () => {
  it('replaceInputBookend preserves middle nodes and topology', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)

    const swapped = replaceInputBookend(model, {
      type: 'JSONInput',
      data: { text: '{}' },
    })

    expect(swapped.inputNode.type).toBe('JSONInput')
    expect(swapped.inputNode.id).toBe('input-1')
    expect(swapped.middleNodes).toHaveLength(1)
    expect(swapped.branchChildren['input-1']).toEqual(['place-1'])
  })

  it('canReplaceOutputBookend checks tip compatibility', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const model = addSiblingBranch(bookends(), 'input-1', place)
    expect(canReplaceOutputBookend(model, 'Output').ok).toBe(true)
  })

  it('clearMiddleNodes preserves bookends and removes middle topology', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = insertAfter(model, 'place-1', { id: 'geo-1', type: 'GeocodeAgent', data: {} })

    const cleared = clearMiddleNodes(model)

    expect(cleared.inputNode.id).toBe(model.inputNode.id)
    expect(cleared.inputNode.type).toBe(model.inputNode.type)
    expect(cleared.outputNode.id).toBe(model.outputNode.id)
    expect(cleared.outputNode.type).toBe(model.outputNode.type)
    expect(cleared.middleNodes).toHaveLength(0)
    expect(cleared.branchChildren).toEqual({})
    expect(cleared.serialLinks).toEqual({})
    expect(edgeSet(cleared)).toEqual(new Set(['input-1->output-1:tip']))
  })

  it('isMiddleNodeId identifies scaffold nodes only', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const model = addSiblingBranch(bookends(), 'input-1', place)
    expect(isMiddleNodeId(model, 'place-1')).toBe(true)
    expect(isMiddleNodeId(model, 'input-1')).toBe(false)
    expect(isMiddleNodeId(model, 'output-1')).toBe(false)
  })

  it('roundtrips a guided graph through modelToGraphSpec and hydrateFromSpec', () => {
    const place: FlowGraphNode = { id: 'place-1', type: 'PlaceExtract', data: {} }
    const place2: FlowGraphNode = { id: 'place-2', type: 'PlaceExtract', data: {} }
    const geocode: FlowGraphNode = { id: 'geo-1', type: 'GeocodeAgent', data: {} }
    let model = addSiblingBranch(bookends(), 'input-1', place)
    model = addSiblingBranch(model, 'input-1', place2)
    model = insertAfter(model, 'place-1', geocode)

    const spec = modelToGraphSpec(model)
    const hydrated = hydrateFromSpec({
      nodes: spec.nodes,
      edges: spec.edges,
    })
    expect(hydrated.ok).toBe(true)
    if (!hydrated.ok) return

    expect(hydrated.model.middleNodes.map((n) => n.id).sort()).toEqual(
      ['geo-1', 'place-1', 'place-2'],
    )
    expect(edgeSet(hydrated.model)).toEqual(edgeSet(model))
  })

  it('rejects graphs without a single input bookend', () => {
    const result = hydrateFromSpec({
      nodes: [{ id: 'output-1', type: 'Output', params: {} }],
      edges: [],
    })
    expect(result.ok).toBe(false)
    if (result.ok) return
    expect(result.title).toMatch(/missing content source/i)
  })
})
