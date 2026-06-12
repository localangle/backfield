import { nodeMetadata } from '@/nodes/registry'
import {
  INPUT_NODE_TYPES,
  isInputBookendType,
  isOutputBookendType,
} from '@/lib/flowValidation'

export type NodeMetadataEntry = (typeof nodeMetadata)[number]

export type CompatibleNodeEntry = {
  type: string
  label: string
  description: string
  category: string
  enabled: boolean
  reason: string | null
}

export type CompatibleNextNodesResult = {
  enabled: CompatibleNodeEntry[]
  disabled: CompatibleNodeEntry[]
}

export type CompatibleNodesOptions = {
  /** Capability name → true when at least one project model is enabled (e.g. embedding). */
  projectModelCapabilities?: Record<string, boolean>
}

function requiredProjectModelCapabilities(meta: NodeMetadataEntry): string[] {
  const caps = (meta as { requiredProjectModelCapabilities?: string[] })
    .requiredProjectModelCapabilities
  return Array.isArray(caps) ? caps : []
}

function missingProjectModelsReason(capabilities: string[]): string {
  if (capabilities.includes('embedding') && capabilities.includes('generative')) {
    return 'Enable generative and embedding models for this project in Models.'
  }
  if (capabilities.includes('embedding')) {
    return 'Enable at least one embedding model for this project in Models.'
  }
  if (capabilities.includes('generative')) {
    return 'Enable at least one generative model for this project in Models.'
  }
  return 'Enable the required models for this project in Models.'
}

function projectModelsRequirementMet(
  meta: NodeMetadataEntry,
  options?: CompatibleNodesOptions,
): { ok: true } | { ok: false; reason: string } {
  const required = requiredProjectModelCapabilities(meta)
  if (required.length === 0) return { ok: true }

  const availability = options?.projectModelCapabilities
  if (availability === undefined) {
    return { ok: false, reason: 'Loading project models…' }
  }

  if (required.every((cap) => availability[cap] === true)) {
    return { ok: true }
  }

  return { ok: false, reason: missingProjectModelsReason(required) }
}

const CATEGORY_HEADINGS: Record<string, string> = {
  extraction: 'Extract information',
  enrichment: 'Enrich and refine',
  geography: 'Geography',
  filter: 'Filter results',
  review: 'Review results',
  embedding: 'Embed',
  text: 'Text analysis',
  output: 'Output',
  input: 'Input',
  control: 'Other',
  other: 'Other',
}

function isBookendType(type: string): boolean {
  return isInputBookendType(type) || isOutputBookendType(type)
}

export function categoryHeading(category: string): string {
  return CATEGORY_HEADINGS[category] ?? category.replace(/_/g, ' ')
}

function typesCompatible(outputType: string, inputType: string): boolean {
  if (inputType === 'any' || outputType === 'any') return true
  if (outputType === inputType) return true
  if (inputType === 'object' && (outputType === 'object' || outputType === 'array')) return true
  // JSONInput (and similar) emit article-shaped objects on the text port; extract nodes
  // declare string but resolve body text from object.text at runtime (see executor tests).
  if (inputType === 'string' && outputType === 'object') return true
  return false
}

/** Sync-barrier nodes accept any upstream output in the guided flow builder. */
export const SYNC_BARRIER_NODE_TYPES = new Set(['Gather'])

/** Pick source/target handle ids for a guided edge from node metadata ports. */
export function resolveEdgeHandles(
  sourceType: string,
  targetType: string,
): { sourceHandle: string; targetHandle: string } | null {
  const sourceMeta = nodeMetadata.find((m) => m.type === sourceType)
  const targetMeta = nodeMetadata.find((m) => m.type === targetType)
  if (!sourceMeta || !targetMeta) return null

  const outputs = sourceMeta.outputs ?? []
  let inputs = targetMeta.inputs ?? []

  if (inputs.length === 0 && SYNC_BARRIER_NODE_TYPES.has(targetType)) {
    inputs = [{ id: 'data', label: 'Any data', type: 'any', required: false }]
  }

  if (outputs.length === 0) return null
  if (inputs.length === 0) return null

  const requiredInputs = inputs.filter((input) => input.required)
  const inputsToTry = requiredInputs.length > 0 ? requiredInputs : inputs

  for (const input of inputsToTry) {
    const compatible = outputs.filter((output) =>
      typesCompatible(String(output.type), String(input.type)),
    )
    if (compatible.length === 0) continue

    const sameId = compatible.find((output) => output.id === input.id)
    if (sameId) {
      return { sourceHandle: sameId.id, targetHandle: input.id }
    }

    if (input.type === 'any' || input.type === 'object') {
      const preferred =
        compatible.find((output) => output.id === 'locations') ??
        compatible.find((output) => output.id === 'places') ??
        compatible.find((output) => output.id === 'people') ??
        compatible.find((output) => output.type === 'array' || output.type === 'object') ??
        compatible[compatible.length - 1]
      return { sourceHandle: preferred.id, targetHandle: input.id }
    }

    return { sourceHandle: compatible[0].id, targetHandle: input.id }
  }

  return null
}

function parentOutputsCompatible(
  parentMeta: NodeMetadataEntry,
  candidateMeta: NodeMetadataEntry,
): boolean {
  if (SYNC_BARRIER_NODE_TYPES.has(candidateMeta.type)) {
    return (parentMeta.outputs ?? []).length > 0
  }

  const outputs = parentMeta.outputs ?? []
  const requiredInputs = (candidateMeta.inputs ?? []).filter((i) => i.required)
  const inputsToCheck =
    requiredInputs.length > 0 ? requiredInputs : (candidateMeta.inputs ?? [])

  if (inputsToCheck.length === 0) return true
  if (outputs.length === 0) return false

  return inputsToCheck.every((input) =>
    outputs.some((output) => typesCompatible(String(output.type), String(input.type))),
  )
}

function upstreamRequirementsMet(
  required: readonly string[],
  ancestryTypes: readonly string[],
): boolean {
  if (required.length === 0) return true
  return required.some((req) => ancestryTypes.includes(req))
}

function upstreamFailureReason(
  meta: NodeMetadataEntry,
  ancestryTypes: readonly string[],
): string {
  const required = meta.requiredUpstreamNodes ?? []
  if (required.length === 0) return ''

  const labels = required
    .map((type) => nodeMetadata.find((m) => m.type === type)?.label ?? type)
    .join(' or ')

  if (meta.dependencyHelperText) {
    return meta.dependencyHelperText
  }

  const hasInput = ancestryTypes.some((t) =>
    (INPUT_NODE_TYPES as readonly string[]).includes(t),
  )
  if (hasInput && required.length > 0) {
    return `Add ${labels} earlier in this branch first.`
  }

  return `Requires ${labels} earlier in this branch.`
}

function portFailureReason(parentMeta: NodeMetadataEntry, candidateMeta: NodeMetadataEntry): string {
  const parentLabel = parentMeta.label ?? parentMeta.type
  const candidateLabel = candidateMeta.label ?? candidateMeta.type
  return `${candidateLabel} cannot use the data coming from ${parentLabel}. Add a different step in between.`
}

function downstreamFailureReason(candidateMeta: NodeMetadataEntry, targetMeta: NodeMetadataEntry): string {
  const candidateLabel = candidateMeta.label ?? candidateMeta.type
  const targetLabel = targetMeta.label ?? targetMeta.type
  return `${targetLabel} cannot use the data coming from ${candidateLabel}. Choose a different step for this connection.`
}

function sameTypeChainFailureReason(meta: NodeMetadataEntry): string {
  const label = meta.label ?? meta.type
  return `${label} cannot follow another ${label} step.`
}

// Each instance classifies/extracts a different dimension or record type, so
// serial chains of the same step are intentional.
export const SAME_TYPE_CHAIN_EXEMPT_NODE_TYPES = new Set(['ArticleMetadata', 'CustomExtract'])

function blocksSameTypeChain(
  candidateType: string,
  upstreamType: string,
): boolean {
  if (SAME_TYPE_CHAIN_EXEMPT_NODE_TYPES.has(candidateType)) {
    return false
  }
  return candidateType === upstreamType
}

function toEntry(
  meta: NodeMetadataEntry,
  enabled: boolean,
  reason: string | null,
): CompatibleNodeEntry {
  return {
    type: meta.type,
    label: meta.label ?? meta.type,
    description: meta.description ?? '',
    category: meta.category ?? 'other',
    enabled,
    reason,
  }
}

export function getCompatibleNextNodes(
  parentType: string,
  branchAncestryTypes: readonly string[],
  options?: CompatibleNodesOptions,
): CompatibleNextNodesResult {
  const parentMeta = nodeMetadata.find((m) => m.type === parentType)
  if (!parentMeta) {
    return { enabled: [], disabled: [] }
  }

  const enabled: CompatibleNodeEntry[] = []
  const disabled: CompatibleNodeEntry[] = []

  for (const meta of nodeMetadata) {
    if (isBookendType(meta.type)) continue
    if ((meta as { enabled?: boolean }).enabled === false) continue

    const ancestryWithParent = branchAncestryTypes.includes(parentType)
      ? branchAncestryTypes
      : [...branchAncestryTypes, parentType]

    const required = meta.requiredUpstreamNodes ?? []
    if (!upstreamRequirementsMet(required, ancestryWithParent)) {
      disabled.push(toEntry(meta, false, upstreamFailureReason(meta, ancestryWithParent)))
      continue
    }

    if (!parentOutputsCompatible(parentMeta, meta)) {
      disabled.push(toEntry(meta, false, portFailureReason(parentMeta, meta)))
      continue
    }

    if (blocksSameTypeChain(meta.type, parentType)) {
      disabled.push(toEntry(meta, false, sameTypeChainFailureReason(meta)))
      continue
    }

    const modelRequirement = projectModelsRequirementMet(meta, options)
    if (!modelRequirement.ok) {
      disabled.push(toEntry(meta, false, modelRequirement.reason))
      continue
    }

    enabled.push(toEntry(meta, true, null))
  }

  enabled.sort((a, b) => a.label.localeCompare(b.label))
  disabled.sort((a, b) => a.label.localeCompare(b.label))

  return { enabled, disabled }
}

export function getCompatibleInsertNodes(
  sourceType: string,
  targetType: string,
  sourceAncestryTypes: readonly string[],
  options?: CompatibleNodesOptions,
): CompatibleNextNodesResult {
  const sourceMeta = nodeMetadata.find((m) => m.type === sourceType)
  const targetMeta = nodeMetadata.find((m) => m.type === targetType)
  if (!sourceMeta || !targetMeta) {
    return { enabled: [], disabled: [] }
  }

  const enabled: CompatibleNodeEntry[] = []
  const disabled: CompatibleNodeEntry[] = []
  const ancestryWithSource = sourceAncestryTypes.includes(sourceType)
    ? sourceAncestryTypes
    : [...sourceAncestryTypes, sourceType]

  for (const meta of nodeMetadata) {
    if (isBookendType(meta.type)) continue
    if ((meta as { enabled?: boolean }).enabled === false) continue

    const candidateRequired = meta.requiredUpstreamNodes ?? []
    if (!upstreamRequirementsMet(candidateRequired, ancestryWithSource)) {
      disabled.push(toEntry(meta, false, upstreamFailureReason(meta, ancestryWithSource)))
      continue
    }

    if (!parentOutputsCompatible(sourceMeta, meta)) {
      disabled.push(toEntry(meta, false, portFailureReason(sourceMeta, meta)))
      continue
    }

    if (blocksSameTypeChain(meta.type, sourceType) || blocksSameTypeChain(meta.type, targetType)) {
      disabled.push(toEntry(meta, false, sameTypeChainFailureReason(meta)))
      continue
    }

    if (!parentOutputsCompatible(meta, targetMeta)) {
      disabled.push(toEntry(meta, false, downstreamFailureReason(meta, targetMeta)))
      continue
    }

    const targetRequired = targetMeta.requiredUpstreamNodes ?? []
    const targetAncestry = [...ancestryWithSource, meta.type]
    if (!upstreamRequirementsMet(targetRequired, targetAncestry)) {
      disabled.push(toEntry(meta, false, upstreamFailureReason(targetMeta, targetAncestry)))
      continue
    }

    const modelRequirement = projectModelsRequirementMet(meta, options)
    if (!modelRequirement.ok) {
      disabled.push(toEntry(meta, false, modelRequirement.reason))
      continue
    }

    enabled.push(toEntry(meta, true, null))
  }

  enabled.sort((a, b) => a.label.localeCompare(b.label))
  disabled.sort((a, b) => a.label.localeCompare(b.label))

  return { enabled, disabled }
}
