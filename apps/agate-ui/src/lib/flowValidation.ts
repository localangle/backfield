import { stripJsonInputEditorMarkers } from '@/lib/jsonInputValidation'
import { resolvedStylebookId } from '@/lib/nodePanelAiModel'
import { isValidS3BucketName, normalizeS3BucketName, normalizeS3FolderPath, normalizeS3MaxFilesInput, S3_DEFAULT_MAX_FILES, s3BucketFieldError } from '@/lib/s3InputValidation'
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

export function isInputNodeType(type: string | undefined): boolean {
  return type != null && (INPUT_NODE_TYPES as readonly string[]).includes(type)
}

export function isInputBookendType(type: string | undefined): boolean {
  return type != null && (INPUT_BOOKEND_TYPES as readonly string[]).includes(type)
}

export function isOutputBookendType(type: string | undefined): boolean {
  return type != null && (OUTPUT_BOOKEND_TYPES as readonly string[]).includes(type)
}

export function validateS3InputBuckets(nodes: FlowGraphNode[]): FlowValidationResult {
  const invalid = nodes.filter(
    (n) => n.type === 'S3Input' && !isValidS3BucketName(String(n.data?.bucket ?? '')),
  )
  if (invalid.length === 0) {
    return { ok: true }
  }

  const bucket = String(invalid[0].data?.bucket ?? '')
  return {
    ok: false,
    title: 'S3 bucket required',
    description: s3BucketFieldError(bucket) ?? 'Fix the S3 bucket name before saving.',
    severity: 'error',
  }
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
  if (node.type === 'S3Input') {
    raw = {
      ...raw,
      bucket: normalizeS3BucketName(String(raw.bucket ?? '')),
      folder_path: normalizeS3FolderPath(String(raw.folder_path ?? '')),
      max_files: normalizeS3MaxFilesInput(String(raw.max_files ?? S3_DEFAULT_MAX_FILES)),
    }
  }
  return raw
}

/** Clear or remap a stale persisted stylebook id before graph save. */
export function sanitizeNodeStylebookRef(
  nodeType: string | undefined,
  params: Record<string, unknown>,
  validStylebookIds: ReadonlySet<number>,
  defaultStylebookId: number | null,
): Record<string, unknown> {
  const sid = resolvedStylebookId(params)
  if (sid == null || validStylebookIds.has(sid)) {
    return params
  }

  const out = { ...params }
  if (nodeType === 'DBOutput') {
    out.stylebook_id = null
    delete out.stylebookId
    return out
  }

  if (nodeType === 'GeocodeAgent') {
    if (out.useCache === true && defaultStylebookId != null) {
      out.stylebook_id = defaultStylebookId
    } else {
      delete out.stylebook_id
    }
    delete out.stylebookId
    return out
  }

  if (defaultStylebookId != null) {
    out.stylebook_id = defaultStylebookId
  } else {
    delete out.stylebook_id
  }
  delete out.stylebookId
  return out
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

export function validateCustomExtractRecordTypes(graph: FlowGraph): FlowValidationResult {
  const seen = new Map<string, number>()
  for (const node of graph.nodes) {
    if (node.type !== 'CustomExtract') continue
    const recordType = String(node.data?.record_type ?? '').trim()
    if (!recordType) continue
    seen.set(recordType, (seen.get(recordType) ?? 0) + 1)
  }

  const duplicates = [...seen.entries()]
    .filter(([, count]) => count > 1)
    .map(([recordType]) => recordType)
  if (duplicates.length === 0) {
    return { ok: true }
  }

  return {
    ok: false,
    title: 'Custom Extract steps overlap',
    description: `More than one Custom Extract step uses the same record type (${duplicates.join(
      ', ',
    )}), so one step's records would overwrite the other's. Give each step its own record type.`,
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
    validateCustomExtractRecordTypes,
    (g) => validateS3InputBuckets(g.nodes),
  ]

  for (const check of checks) {
    const result = check(graph)
    if (!result.ok) {
      return result
    }
  }
  return { ok: true }
}
