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

export function categoryHeading(category: string): string {
  return CATEGORY_HEADINGS[category] ?? category.replace(/_/g, ' ')
}

function isBookendType(type: string): boolean {
  return (
    (INPUT_BOOKEND_TYPES as readonly string[]).includes(type) ||
    (OUTPUT_BOOKEND_TYPES as readonly string[]).includes(type) ||
    type === 'S3Output'
  )
}

function typesCompatible(outputType: string, inputType: string): boolean {
  if (inputType === 'any' || outputType === 'any') return true
  if (outputType === inputType) return true
  if (inputType === 'object' && (outputType === 'object' || outputType === 'array')) return true
  return false
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
