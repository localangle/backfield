import { describe, expect, it } from 'vitest'
import {
  addSiblingBranch,
  assignLayoutPositions,
  clearMiddleNodes,
  createFlowGraphModel,
  deleteMiddleNode,
  deriveEdges,
  getBranchAncestry,
  getBranchTipIds,
  hydrateFromSpec,
  insertAfter,
  insertBetween,
  isMiddleNodeId,
  modelToGraphSpec,
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
