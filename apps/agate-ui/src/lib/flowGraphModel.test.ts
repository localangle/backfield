import { describe, expect, it } from 'vitest'
import {
  addSiblingBranch,
  assignLayoutPositions,
  createFlowGraphModel,
  deriveEdges,
  getBranchAncestry,
  getBranchTipIds,
  insertAfter,
  insertBetween,
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
