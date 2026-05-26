import { nodeMetadata } from '@/nodes/registry'
import { INPUT_BOOKEND_TYPES, OUTPUT_BOOKEND_TYPES } from '@/lib/flowValidation'

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

const INPUT_NODE_TYPES = [...INPUT_BOOKEND_TYPES, 'APIInput', 'DBInput'] as const

const CATEGORY_HEADINGS: Record<string, string> = {
  extraction: 'Extract information',
  enrichment: 'Enrich and refine',
  geography: 'Geography',
  filter: 'Filter results',
  review: 'Review results',
  text: 'Text analysis',
  output: 'Output',
  input: 'Input',
}

/** Show search in the "+" chooser when the scaffold node catalog exceeds this count. */
export const CHOOSER_SEARCH_NODE_THRESHOLD = 8

export function shouldShowChooserSearch(scaffoldNodeTypeCount: number): boolean {
  return scaffoldNodeTypeCount > CHOOSER_SEARCH_NODE_THRESHOLD
}

export function countScaffoldNodeTypes(): number {
  return nodeMetadata.filter(
    (meta) => meta.enabled !== false && !isBookendType(String(meta.type)),
  ).length
}

function isBookendType(type: string): boolean {
  return (
    (INPUT_BOOKEND_TYPES as readonly string[]).includes(type) ||
    (OUTPUT_BOOKEND_TYPES as readonly string[]).includes(type) ||
    type === 'S3Output'
  )
}

export function categoryHeading(category: string): string {
  return CATEGORY_HEADINGS[category] ?? category.replace(/_/g, ' ')
}

function typesCompatible(outputType: string, inputType: string): boolean {
  if (inputType === 'any' || outputType === 'any') return true
  if (outputType === inputType) return true
  if (inputType === 'object' && (outputType === 'object' || outputType === 'array')) return true
  return false
}

/** Pick source/target handle ids for a guided edge from node metadata ports. */
export function resolveEdgeHandles(
  sourceType: string,
  targetType: string,
): { sourceHandle: string; targetHandle: string } | null {
  const sourceMeta = nodeMetadata.find((m) => m.type === sourceType)
  const targetMeta = nodeMetadata.find((m) => m.type === targetType)
  if (!sourceMeta || !targetMeta) return null

  const outputs = sourceMeta.outputs ?? []
  const inputs = targetMeta.inputs ?? []
  if (outputs.length === 0 || inputs.length === 0) return null

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

    enabled.push(toEntry(meta, true, null))
  }

  enabled.sort((a, b) => a.label.localeCompare(b.label))
  disabled.sort((a, b) => a.label.localeCompare(b.label))

  return { enabled, disabled }
}
