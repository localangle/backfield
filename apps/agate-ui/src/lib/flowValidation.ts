import { stripJsonInputEditorMarkers } from '@/lib/jsonInputValidation'
import { nodeMetadata } from '@/nodes/registry'

/** Guided builder: exactly one of these per flow. */
export const INPUT_BOOKEND_TYPES = ['TextInput', 'JSONInput', 'S3Input'] as const
export type InputBookendType = (typeof INPUT_BOOKEND_TYPES)[number]

/** All node types treated as flow inputs (wiring rules). */
export const INPUT_NODE_TYPES = [
  ...INPUT_BOOKEND_TYPES,
  'APIInput',
  'DBInput',
] as const

/** Guided builder: exactly one of these per flow. */
export const OUTPUT_BOOKEND_TYPES = ['Output', 'DBOutput'] as const
export type OutputBookendType = (typeof OUTPUT_BOOKEND_TYPES)[number]

/** All node types treated as flow outputs (presence checks). */
export const OUTPUT_NODE_TYPES = [...OUTPUT_BOOKEND_TYPES, 'S3Output'] as const

export type FlowValidationSeverity = 'warning' | 'error'

export type FlowValidationFailure = {
  ok: false
  title: string
  description: string
  severity: FlowValidationSeverity
}

export type FlowValidationResult = { ok: true } | FlowValidationFailure

export type FlowGraphNode = {
  id: string
  type?: string
  data?: Record<string, unknown>
}

export type FlowGraphEdge = {
  source: string
  target: string
}

export type FlowGraph = {
  nodes: FlowGraphNode[]
  edges: FlowGraphEdge[]
}

function nodeDisplayLabel(type: string | undefined): string {
  if (!type) return 'Step'
  const meta = nodeMetadata.find((m) => m.type === type)
  return meta?.label ?? 'Step'
}

function formatNodeList(nodes: FlowGraphNode[]): string {
  return nodes.map((n) => nodeDisplayLabel(n.type)).join(', ')
}

function isInputNodeType(type: string | undefined): boolean {
  return type != null && (INPUT_NODE_TYPES as readonly string[]).includes(type)
}

function isInputBookendType(type: string | undefined): boolean {
  return type != null && (INPUT_BOOKEND_TYPES as readonly string[]).includes(type)
}

function isOutputBookendType(type: string | undefined): boolean {
  return type != null && (OUTPUT_BOOKEND_TYPES as readonly string[]).includes(type)
}

export function geocodeStylebookIdFromData(
  data: Record<string, unknown> | undefined,
): number | null {
  if (!data) return null
  const snake = data.stylebook_id
  const camel = data.stylebookId
  const raw = snake !== undefined && snake !== null ? snake : camel
  if (raw === null || raw === undefined || raw === '') return null
  const n = typeof raw === 'number' ? raw : Number(raw)
  return Number.isFinite(n) ? n : null
}

/** Catalog required when Geocode cache is on (persisted as ``stylebook_id``). */
export function validateGeocodeCatalogSelection(
  nodes: FlowGraphNode[],
): FlowValidationResult {
  for (const node of nodes) {
    if (node.type !== 'GeocodeAgent') continue
    const d = node.data ?? {}
    if (!d.useCache) continue
    if (geocodeStylebookIdFromData(d) == null) {
      return {
        ok: false,
        title: 'Catalog required',
        description:
          'Turn on catalog selection for Geocode: open each Geocode step with cache turned on and pick a catalog.',
        severity: 'warning',
      }
    }
  }
  return { ok: true }
}

export function paramsForGraphSave(node: FlowGraphNode): Record<string, unknown> {
  let raw = { ...(node.data ?? {}) }
  if (node.type === 'JSONInput') {
    raw = stripJsonInputEditorMarkers(raw)
  }
  if (node.type === 'GeocodeAgent') {
    delete raw.stylebookId
    if (!raw.useCache) {
      delete raw.stylebook_id
    }
  }
  return raw
}

export function validateSingleBookends(graph: FlowGraph): FlowValidationResult {
  const inputBookends = graph.nodes.filter((n) => isInputBookendType(n.type))
  if (inputBookends.length === 0) {
    return {
      ok: false,
      title: 'Missing content source',
      description: 'Your flow needs one place where content comes in.',
      severity: 'warning',
    }
  }
  if (inputBookends.length > 1) {
    return {
      ok: false,
      title: 'Too many content sources',
      description: 'Your flow can only have one content source. Remove the extra input steps.',
      severity: 'warning',
    }
  }

  const outputBookends = graph.nodes.filter((n) => isOutputBookendType(n.type))
  if (outputBookends.length === 0) {
    return {
      ok: false,
      title: 'Missing results destination',
      description: 'Your flow needs one place where results go.',
      severity: 'warning',
    }
  }
  if (outputBookends.length > 1) {
    return {
      ok: false,
      title: 'Too many outputs',
      description: 'Your flow can only have one output. Remove the extra output steps.',
      severity: 'warning',
    }
  }

  return { ok: true }
}

export function validateFlowInputOutputRules(graph: FlowGraph): FlowValidationResult {
  const bookendResult = validateSingleBookends(graph)
  if (!bookendResult.ok) {
    return bookendResult
  }

  const hasS3Input = graph.nodes.some((n) => n.type === 'S3Input')
  const hasAPIInput = graph.nodes.some((n) => n.type === 'APIInput')
  if (hasS3Input && hasAPIInput) {
    return {
      ok: false,
      title: 'Invalid input setup',
      description: 'Your flow cannot use both S3 and API input at the same time. Choose one content source.',
      severity: 'error',
    }
  }

  if (hasAPIInput) {
    const apiInputNodes = graph.nodes.filter((n) => n.type === 'APIInput')
    const nodesWithIncoming = new Set(graph.edges.map((e) => e.target))
    const apiInputNotFirst = apiInputNodes.some((n) => nodesWithIncoming.has(n.id))
    if (apiInputNotFirst) {
      return {
        ok: false,
        title: 'API input must come first',
        description: 'The API input step must be the first step in your flow with no steps before it.',
        severity: 'error',
      }
    }
  }

  return { ok: true }
}

export function validateNoOrphans(graph: FlowGraph): FlowValidationResult {
  const connectedNodeIds = new Set<string>()
  for (const edge of graph.edges) {
    connectedNodeIds.add(edge.source)
    connectedNodeIds.add(edge.target)
  }

  const orphanNodes = graph.nodes.filter((n) => !connectedNodeIds.has(n.id))
  if (orphanNodes.length === 0) {
    return { ok: true }
  }

  return {
    ok: false,
    title: 'Disconnected steps',
    description: `These steps are not connected to your flow: ${formatNodeList(orphanNodes)}. Connect or remove them before saving.`,
    severity: 'warning',
  }
}

export function validateInputConnections(graph: FlowGraph): FlowValidationResult {
  const nodesWithIncoming = new Set(graph.edges.map((e) => e.target))
  const nodesWithoutInput = graph.nodes.filter((n) => {
    if (isInputNodeType(n.type)) {
      return false
    }
    return !nodesWithIncoming.has(n.id)
  })

  if (nodesWithoutInput.length === 0) {
    return { ok: true }
  }

  return {
    ok: false,
    title: 'Steps missing input',
    description: `These steps are not receiving data from an earlier step: ${formatNodeList(nodesWithoutInput)}. Connect each processing step to the step before it.`,
    severity: 'warning',
  }
}

/** Run all graph save validations; returns the first failure or success. */
export function validateGraphForSave(graph: FlowGraph): FlowValidationResult {
  const checks: Array<(g: FlowGraph) => FlowValidationResult> = [
    validateFlowInputOutputRules,
    validateNoOrphans,
    validateInputConnections,
    (g) => validateGeocodeCatalogSelection(g.nodes),
  ]

  for (const check of checks) {
    const result = check(graph)
    if (!result.ok) {
      return result
    }
  }
  return { ok: true }
}
