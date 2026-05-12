/**
 * Run `result` / `node_outputs` objects use stable snake_case keys per node type
 * (e.g. `geocode_agent`, `json_output`, `stylebook_output`), matching `execute_graph`.
 * Legacy payloads may still include `__outputKeysByNodeId` plus human-readable keys.
 *
 * Canonical copy for Agate UI and agate-runtime node sources
 * (via `@/lib/nodeOutputs` re-export in synced panels).
 */

export const NODE_OUTPUT_KEY_INDEX = '__outputKeysByNodeId' as const

const NODE_TYPE_OUTPUT_SLUGS: Record<string, string> = {
  Output: 'json_output',
  DBOutput: 'stylebook_output',
}

export type NodeOutputLookupSpec = {
  nodes: Array<{ id: string; type: string }>
  edges: Array<{ source: string; target: string }>
}

function nodeTypeToOutputSlug(nodeType: string): string {
  if (NODE_TYPE_OUTPUT_SLUGS[nodeType]) {
    return NODE_TYPE_OUTPUT_SLUGS[nodeType]
  }
  const s1 = nodeType.replace(/(.)([A-Z][a-z]+)/g, '$1_$2')
  const s2 = s1.replace(/([a-z0-9])([A-Z])/g, '$1_$2')
  return s2.toLowerCase()
}

function topoOrder(
  nodeIds: string[],
  edges: Array<{ source: string; target: string }>,
): string[] {
  const nodeSet = new Set(nodeIds)
  const inDegree = new Map<string, number>()
  const outgoing = new Map<string, string[]>()
  for (const id of nodeIds) {
    inDegree.set(id, 0)
    outgoing.set(id, [])
  }
  for (const e of edges) {
    if (!nodeSet.has(e.source) || !nodeSet.has(e.target)) continue
    inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1)
    outgoing.get(e.source)!.push(e.target)
  }
  const queue: string[] = []
  for (const id of nodeIds) {
    if ((inDegree.get(id) ?? 0) === 0) queue.push(id)
  }
  const order: string[] = []
  while (queue.length) {
    const u = queue.shift()!
    order.push(u)
    for (const v of outgoing.get(u) ?? []) {
      const nd = (inDegree.get(v) ?? 0) - 1
      inDegree.set(v, nd)
      if (nd === 0) queue.push(v)
    }
  }
  if (order.length !== nodeIds.length) {
    throw new Error('Graph has a cycle or invalid edges for topo sort')
  }
  return order
}

/** Match `execute_graph` / `_public_node_output_keys` in `agate_runtime.executor`. */
export function buildNodeIdToPublicOutputKey(spec: NodeOutputLookupSpec): Record<string, string> {
  const byId = new Map(spec.nodes.map((n) => [n.id, n]))
  const order = topoOrder(
    spec.nodes.map((n) => n.id),
    spec.edges,
  )
  const perBaseCount = new Map<string, number>()
  const idToPublic: Record<string, string> = {}
  const usedPublic = new Set<string>()

  for (const nid of order) {
    const node = byId.get(nid)
    if (!node) continue
    const base = nodeTypeToOutputSlug(node.type)
    const c = (perBaseCount.get(base) ?? 0) + 1
    perBaseCount.set(base, c)
    let pub = c === 1 ? base : `${base}_${nid}`
    if (usedPublic.has(pub)) {
      pub = nid
    }
    usedPublic.add(pub)
    idToPublic[nid] = pub
  }
  return idToPublic
}

export function getNodeOutputKeyMap(
  raw: Record<string, unknown> | null | undefined,
): Record<string, string> | null {
  if (!raw) return null
  const m = raw[NODE_OUTPUT_KEY_INDEX]
  if (m && typeof m === 'object' && !Array.isArray(m)) {
    return m as Record<string, string>
  }
  return null
}

/** Resolve a node's output dict; supports legacy results and slug keys with an optional graph spec. */
export function getNodeOutputById(
  raw: Record<string, unknown> | null | undefined,
  nodeId: string,
  graphSpec?: NodeOutputLookupSpec | null,
): unknown {
  if (!raw) return undefined

  const legacyMap = getNodeOutputKeyMap(raw)
  if (legacyMap) {
    const pub = legacyMap[nodeId]
    if (pub !== undefined && Object.prototype.hasOwnProperty.call(raw, pub)) {
      return raw[pub]
    }
  }

  if (graphSpec?.nodes?.length) {
    try {
      const keys = buildNodeIdToPublicOutputKey(graphSpec)
      const pub = keys[nodeId]
      if (pub !== undefined && Object.prototype.hasOwnProperty.call(raw, pub)) {
        return raw[pub]
      }
    } catch {
      /* invalid spec — fall through */
    }
  }

  if (Object.prototype.hasOwnProperty.call(raw, nodeId)) {
    return raw[nodeId]
  }
  return undefined
}

/** Build lookup spec from an Agate API graph `spec` (nodes + optional edges). */
export function nodeOutputLookupFromGraphSpec(spec: {
  nodes: Array<{ id: string; type: string }>
  edges?: Array<{ source: string; target: string }> | null
}): NodeOutputLookupSpec {
  return {
    nodes: spec.nodes.map((n) => ({ id: n.id, type: n.type })),
    edges: (spec.edges ?? []).map((e) => ({ source: e.source, target: e.target })),
  }
}

/** Build lookup spec from React Flow `nodes` / `edges` (canvas state). */
export function nodeOutputLookupFromReactFlow(
  nodes: Array<{ id: string; type?: string | null }>,
  edges: Array<{ source: string; target: string }>,
): NodeOutputLookupSpec {
  return {
    nodes: nodes.map((n) => ({ id: n.id, type: n.type! })),
    edges: edges.map((e) => ({ source: e.source, target: e.target })),
  }
}
